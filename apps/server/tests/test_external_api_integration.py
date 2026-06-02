"""Integration tests for external API key backed public endpoints."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy import delete, select

import pandamind.core.auth as auth
from pandamind.core.config import get_settings
from pandamind.db.models import ApiClient, ApiKey, ApiUsageEvent, Conversation, Prompt
from pandamind.db.session import AsyncSessionLocal
from pandamind.main import app
from pandamind.providers.base import ChatChunk, ChatOptions, Message
from pandamind.providers.registry import rebuild_registry

pytestmark = pytest.mark.integration


class FakeProvider:
    model_name = "fake-model"

    async def chat(
        self,
        messages: list[Message],  # noqa: ARG002
        options: ChatOptions,  # noqa: ARG002
    ) -> AsyncIterator[ChatChunk]:
        yield ChatChunk(content="pong", usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})
        yield ChatChunk(content="", done=True, finish_reason="stop")

    async def health_check(self) -> Any:
        raise NotImplementedError

    async def list_models(self) -> list[Any]:
        return []


@pytest.fixture(autouse=True)
def _force_real_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """集成测试必须验证真实鉴权路径，避免本地 AUTH_DISABLED 影响断言。"""

    settings = get_settings()

    class TestSettings:
        auth_disabled = False
        effective_jwt_secret = settings.effective_jwt_secret

    monkeypatch.setattr(auth, "get_settings", lambda: TestSettings())


@pytest.fixture(autouse=True)
async def _clean_external_api_rows() -> AsyncIterator[None]:
    """Keep integration data isolated from local development records."""
    await _cleanup()
    rebuild_registry([])
    yield
    await _cleanup()
    rebuild_registry([])


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


def _admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {auth.create_token('admin')}"}


async def _cleanup() -> None:
    async with AsyncSessionLocal() as session:
        client_ids = (
            await session.execute(
                select(ApiClient.id).where(ApiClient.name == "integration-client")
            )
        ).scalars().all()
        if client_ids:
            await session.execute(delete(ApiUsageEvent).where(ApiUsageEvent.client_id.in_(client_ids)))
            await session.execute(delete(ApiKey).where(ApiKey.client_id.in_(client_ids)))
            await session.execute(delete(ApiClient).where(ApiClient.id.in_(client_ids)))

        await session.execute(delete(Conversation).where(Conversation.model_id == "itest-model"))
        await session.execute(delete(Prompt).where(Prompt.id.like("itest-%")))
        await session.commit()


async def _create_client_and_key(
    client: httpx.AsyncClient,
    *,
    scopes: list[str],
    allowed_model_ids: list[str],
    allowed_prompt_ids: list[str],
) -> tuple[str, str, str]:
    client_res = await client.post(
        "/v1/api-clients",
        headers=_admin_headers(),
        json={"name": "integration-client"},
    )
    assert client_res.status_code == 201, client_res.text
    client_id = client_res.json()["id"]

    key_res = await client.post(
        f"/v1/api-clients/{client_id}/keys",
        headers=_admin_headers(),
        json={
            "name": "integration-key",
            "environment": "test",
            "scopes": scopes,
            "allowed_model_ids": allowed_model_ids,
            "allowed_prompt_ids": allowed_prompt_ids,
        },
    )
    assert key_res.status_code == 201, key_res.text
    body = key_res.json()
    return client_id, body["id"], body["api_key"]


async def _create_prompt(prompt_id: str = "itest-prompt") -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            Prompt(
                id=prompt_id,
                name="Integration prompt",
                system="You are concise.",
                user_template="{{question}}",
                variables=[{"name": "question", "required": True}],
                tags=["integration"],
                version=1,
            )
        )
        await session.commit()


async def test_admin_can_create_client_and_api_key_once(client: httpx.AsyncClient):
    client_id, _, api_key = await _create_client_and_key(
        client,
        scopes=["chat:invoke"],
        allowed_model_ids=["itest-model"],
        allowed_prompt_ids=[],
    )

    assert api_key.startswith("pmk_test_")

    list_res = await client.get("/v1/api-clients", headers=_admin_headers())
    assert list_res.status_code == 200
    assert any(row["name"] == "integration-client" for row in list_res.json())

    keys_res = await client.get(f"/v1/api-clients/{client_id}/keys", headers=_admin_headers())
    assert keys_res.status_code == 200
    assert "api_key" not in keys_res.json()[0]


async def test_public_chat_rejects_missing_or_unauthorized_key(client: httpx.AsyncClient):
    no_token = await client.post(
        "/v1/chat/completions",
        json={"model": "itest-model", "messages": [{"role": "user", "content": "ping"}], "stream": False},
    )
    assert no_token.status_code == 401

    _, _, api_key = await _create_client_and_key(
        client,
        scopes=["chat:invoke"],
        allowed_model_ids=["other-model"],
        allowed_prompt_ids=[],
    )
    forbidden = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "itest-model", "messages": [{"role": "user", "content": "ping"}], "stream": False},
    )
    assert forbidden.status_code == 403
    assert "not allowed" in forbidden.json()["message"]


async def test_public_chat_with_api_key_records_usage(client: httpx.AsyncClient):
    registry = rebuild_registry([])
    registry.register("itest-model", FakeProvider())
    client_id, _, api_key = await _create_client_and_key(
        client,
        scopes=["chat:invoke", "usage:read"],
        allowed_model_ids=["itest-model"],
        allowed_prompt_ids=[],
    )

    res = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "itest-model", "messages": [{"role": "user", "content": "ping"}], "stream": False},
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["choices"][0]["message"]["content"] == "pong"
    assert body["usage"]["total_tokens"] == 2

    usage = await client.get("/v1/public/usage", headers={"Authorization": f"Bearer {api_key}"})
    assert usage.status_code == 200, usage.text
    rows = usage.json()
    assert rows
    assert rows[0]["model_id"] == "itest-model"
    assert rows[0]["total_tokens"] == 2

    async with AsyncSessionLocal() as session:
        events = (
            await session.execute(select(ApiUsageEvent).where(ApiUsageEvent.client_id == client_id))
        ).scalars().all()
        assert len(events) == 1
        assert events[0].client_id == client_id


async def test_public_process_enforces_prompt_access_and_records_usage(client: httpx.AsyncClient):
    registry = rebuild_registry([])
    registry.register("itest-model", FakeProvider())
    await _create_prompt("itest-prompt")
    _, _, api_key = await _create_client_and_key(
        client,
        scopes=["process:invoke", "usage:read"],
        allowed_model_ids=["itest-model"],
        allowed_prompt_ids=["itest-prompt"],
    )

    res = await client.post(
        "/v1/process",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "text": "ping",
            "prompt_id": "itest-prompt",
            "model": "itest-model",
            "variables": {"question": "ping"},
        },
    )

    assert res.status_code == 200, res.text
    assert res.json()["result"] == "pong"

    usage = await client.get("/v1/public/usage", headers={"Authorization": f"Bearer {api_key}"})
    assert usage.status_code == 200, usage.text
    assert usage.json()[0]["prompt_id"] == "itest-prompt"


async def test_disabled_api_key_is_rejected(client: httpx.AsyncClient):
    client_id, key_id, api_key = await _create_client_and_key(
        client,
        scopes=["chat:invoke"],
        allowed_model_ids=["itest-model"],
        allowed_prompt_ids=[],
    )

    disable = await client.post(
        f"/v1/api-clients/{client_id}/keys/{key_id}/disable",
        headers=_admin_headers(),
    )
    assert disable.status_code == 200
    assert disable.json()["status"] == "disabled"

    res = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "itest-model", "messages": [{"role": "user", "content": "ping"}], "stream": False},
    )
    assert res.status_code == 401
