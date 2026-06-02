"""Public API helper endpoints for external API key callers."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pandamind.core.auth import require_external_api_key, require_public_identity
from pandamind.db.models import ApiUsageEvent, ModelConfig, Prompt
from pandamind.db.session import get_session
from pandamind.services.api_keys import ApiIdentity, require_scope

router = APIRouter(prefix="/v1/public", tags=["public"])


@router.get("/models", response_model=list[dict[str, Any]])
async def list_public_models(
    session: AsyncSession = Depends(get_session),
    raw_identity: str | ApiIdentity = Depends(require_public_identity),
) -> list[dict[str, Any]]:
    identity = require_external_api_key(raw_identity)
    try:
        require_scope(identity, "models:list")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None

    if not identity.allowed_model_ids:
        return []

    rows = (
        await session.execute(
            select(ModelConfig).where(ModelConfig.id.in_(identity.allowed_model_ids))
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "provider": row.provider,
            "model": row.model,
            "aliases": row.aliases,
            "enabled": row.enabled,
        }
        for row in rows
    ]


@router.get("/prompts", response_model=list[dict[str, Any]])
async def list_public_prompts(
    session: AsyncSession = Depends(get_session),
    raw_identity: str | ApiIdentity = Depends(require_public_identity),
) -> list[dict[str, Any]]:
    identity = require_external_api_key(raw_identity)
    try:
        require_scope(identity, "prompts:list")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None

    if not identity.allowed_prompt_ids:
        return []

    rows = (
        await session.execute(select(Prompt).where(Prompt.id.in_(identity.allowed_prompt_ids)))
    ).scalars().all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "variables": row.variables,
            "tags": row.tags,
            "version": row.version,
        }
        for row in rows
    ]


@router.get("/usage", response_model=list[dict[str, Any]])
async def list_public_usage(
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    raw_identity: str | ApiIdentity = Depends(require_public_identity),
) -> list[dict[str, Any]]:
    identity = require_external_api_key(raw_identity)
    try:
        require_scope(identity, "usage:read")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e)) from None

    rows = (
        await session.execute(
            select(ApiUsageEvent)
            .where(ApiUsageEvent.api_key_id == identity.api_key_id)
            .order_by(ApiUsageEvent.created_at.desc())
            .limit(min(limit, 500))
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "trace_id": row.trace_id,
            "endpoint": row.endpoint,
            "method": row.method,
            "model_id": row.model_id,
            "prompt_id": row.prompt_id,
            "status_code": row.status_code,
            "error_code": row.error_code,
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "total_tokens": row.total_tokens,
            "provider_latency_ms": row.provider_latency_ms,
            "total_latency_ms": row.total_latency_ms,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
