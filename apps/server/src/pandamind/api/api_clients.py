"""Admin API for external API clients and keys."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pandamind.core.auth import require_auth
from pandamind.core.ids import generate_id
from pandamind.db.models import ApiClient, ApiKey, ApiUsageEvent
from pandamind.db.session import get_session
from pandamind.services.api_keys import generate_api_key

router = APIRouter(prefix="/v1/api-clients", tags=["admin-api-clients"])


def _serialize_client(client: ApiClient) -> dict[str, Any]:
    return {
        "id": client.id,
        "name": client.name,
        "description": client.description,
        "owner_email": client.owner_email,
        "status": client.status,
        "created_at": client.created_at.isoformat() if client.created_at else None,
        "updated_at": client.updated_at.isoformat() if client.updated_at else None,
    }


def _serialize_key(api_key: ApiKey) -> dict[str, Any]:
    return {
        "id": api_key.id,
        "client_id": api_key.client_id,
        "name": api_key.name,
        "key_prefix": api_key.key_prefix,
        "key_last4": api_key.key_last4,
        "environment": api_key.environment,
        "scopes": api_key.scopes,
        "allowed_model_ids": api_key.allowed_model_ids,
        "allowed_prompt_ids": api_key.allowed_prompt_ids,
        "status": api_key.status,
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        "last_used_at": api_key.last_used_at.isoformat() if api_key.last_used_at else None,
        "created_at": api_key.created_at.isoformat() if api_key.created_at else None,
        "updated_at": api_key.updated_at.isoformat() if api_key.updated_at else None,
    }


@router.get("", response_model=list[dict[str, Any]])
async def list_clients(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> list[dict[str, Any]]:
    rows = (await session.execute(select(ApiClient).order_by(ApiClient.created_at.desc()))).scalars().all()
    return [_serialize_client(row) for row in rows]


@router.post("", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_client(
    data: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    client = ApiClient(
        id=generate_id(),
        name=data["name"],
        description=data.get("description"),
        owner_email=data.get("owner_email"),
        status=data.get("status", "active"),
    )
    session.add(client)
    await session.commit()
    await session.refresh(client)
    return _serialize_client(client)


@router.get("/{client_id}/keys", response_model=list[dict[str, Any]])
async def list_client_keys(
    client_id: str,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> list[dict[str, Any]]:
    _ = await _get_client_or_404(session, client_id)
    rows = (
        await session.execute(
            select(ApiKey).where(ApiKey.client_id == client_id).order_by(ApiKey.created_at.desc())
        )
    ).scalars().all()
    return [_serialize_key(row) for row in rows]


@router.post("/{client_id}/keys", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_client_key(
    client_id: str,
    data: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    _ = await _get_client_or_404(session, client_id)
    environment = data.get("environment", "live")
    generated = generate_api_key(environment=environment)
    api_key = ApiKey(
        id=generate_id(),
        client_id=client_id,
        public_id=generated.public_id,
        name=data["name"],
        key_prefix=generated.key_prefix,
        key_hash=generated.key_hash,
        key_last4=generated.key_last4,
        environment=environment,
        scopes=data.get("scopes", []),
        allowed_model_ids=data.get("allowed_model_ids", []),
        allowed_prompt_ids=data.get("allowed_prompt_ids", []),
        allowed_ips=data.get("allowed_ips", []),
        allowed_origins=data.get("allowed_origins", []),
        status=data.get("status", "active"),
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    payload = _serialize_key(api_key)
    payload["api_key"] = generated.plaintext
    return payload


@router.post("/{client_id}/keys/{key_id}/disable", response_model=dict[str, Any])
async def disable_client_key(
    client_id: str,
    key_id: str,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    result = await session.execute(
        select(ApiKey).where(ApiKey.client_id == client_id, ApiKey.id == key_id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    api_key.status = "disabled"
    await session.commit()
    await session.refresh(api_key)
    return _serialize_key(api_key)


@router.get("/{client_id}/usage", response_model=list[dict[str, Any]])
async def list_client_usage(
    client_id: str,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> list[dict[str, Any]]:
    _ = await _get_client_or_404(session, client_id)
    rows = (
        await session.execute(
            select(ApiUsageEvent)
            .where(ApiUsageEvent.client_id == client_id)
            .order_by(ApiUsageEvent.created_at.desc())
            .limit(min(limit, 500))
        )
    ).scalars().all()
    return [_serialize_usage(row) for row in rows]


async def _get_client_or_404(session: AsyncSession, client_id: str) -> ApiClient:
    result = await session.execute(select(ApiClient).where(ApiClient.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="API client not found")
    return client


def _serialize_usage(event: ApiUsageEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "trace_id": event.trace_id,
        "client_id": event.client_id,
        "api_key_id": event.api_key_id,
        "endpoint": event.endpoint,
        "method": event.method,
        "model_id": event.model_id,
        "prompt_id": event.prompt_id,
        "status_code": event.status_code,
        "error_code": event.error_code,
        "prompt_tokens": event.prompt_tokens,
        "completion_tokens": event.completion_tokens,
        "total_tokens": event.total_tokens,
        "provider_latency_ms": event.provider_latency_ms,
        "total_latency_ms": event.total_latency_ms,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
