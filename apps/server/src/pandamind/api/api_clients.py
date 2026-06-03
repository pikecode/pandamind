"""Admin API for external API clients and keys."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pandamind.core.auth import require_auth
from pandamind.core.ids import generate_id
from pandamind.db.models import ApiClient, ApiKey, ApiUsageEvent
from pandamind.db.session import get_session
from pandamind.services.api_keys import generate_api_key

router = APIRouter(prefix="/v1/api-clients", tags=["admin-api-clients"])

ALLOWED_CLIENT_STATUSES = {"active", "disabled"}
ALLOWED_KEY_ENVIRONMENTS = {"live", "test"}
ALLOWED_KEY_STATUSES = {"active", "disabled"}
ALLOWED_SCOPES = {"chat:invoke", "process:invoke", "models:list", "prompts:list", "usage:read"}


class ApiClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    owner_email: str | None = Field(default=None, max_length=255)
    status: str = "active"


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    environment: str = "live"
    scopes: list[str] = Field(default_factory=list)
    allowed_model_ids: list[str] = Field(default_factory=list)
    allowed_prompt_ids: list[str] = Field(default_factory=list)
    allowed_ips: list[str] = Field(default_factory=list)
    allowed_origins: list[str] = Field(default_factory=list)
    status: str = "active"


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
    data: ApiClientCreate,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    if data.status not in ALLOWED_CLIENT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid client status: {data.status}")
    client = ApiClient(
        id=generate_id(),
        name=data.name,
        description=data.description,
        owner_email=data.owner_email,
        status=data.status,
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
    data: ApiKeyCreate,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    _ = await _get_client_or_404(session, client_id)
    if data.environment not in ALLOWED_KEY_ENVIRONMENTS:
        raise HTTPException(status_code=400, detail=f"Invalid key environment: {data.environment}")
    if data.status not in ALLOWED_KEY_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid key status: {data.status}")
    unknown_scopes = sorted(set(data.scopes) - ALLOWED_SCOPES)
    if unknown_scopes:
        raise HTTPException(status_code=400, detail=f"Invalid scopes: {', '.join(unknown_scopes)}")

    environment = data.environment
    generated = generate_api_key(environment=environment)
    api_key = ApiKey(
        id=generate_id(),
        client_id=client_id,
        public_id=generated.public_id,
        name=data.name,
        key_prefix=generated.key_prefix,
        key_hash=generated.key_hash,
        key_last4=generated.key_last4,
        environment=environment,
        scopes=data.scopes,
        allowed_model_ids=data.allowed_model_ids,
        allowed_prompt_ids=data.allowed_prompt_ids,
        allowed_ips=data.allowed_ips,
        allowed_origins=data.allowed_origins,
        status=data.status,
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
