"""External API usage event persistence."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pandamind.core.ids import generate_id
from pandamind.db.models import ApiUsageEvent
from pandamind.services.api_keys import ApiIdentity


async def record_usage_event(
    session: AsyncSession,
    *,
    identity: ApiIdentity,
    trace_id: str,
    endpoint: str,
    method: str,
    model_id: str | None,
    prompt_id: str | None = None,
    status_code: int,
    error_code: str | None = None,
    usage: dict[str, Any] | None = None,
    provider_latency_ms: int | None = None,
    total_latency_ms: int | None = None,
    request_bytes: int | None = None,
    response_bytes: int | None = None,
) -> None:
    """Persist one external API usage event."""
    token_usage = usage or {}
    event = ApiUsageEvent(
        id=generate_id(),
        trace_id=trace_id,
        client_id=identity.client_id,
        api_key_id=identity.api_key_id,
        endpoint=endpoint,
        method=method,
        model_id=model_id,
        prompt_id=prompt_id,
        status_code=status_code,
        error_code=error_code,
        prompt_tokens=token_usage.get("prompt_tokens", 0),
        completion_tokens=token_usage.get("completion_tokens", 0),
        total_tokens=token_usage.get("total_tokens", 0),
        provider_latency_ms=provider_latency_ms,
        total_latency_ms=total_latency_ms,
        request_bytes=request_bytes,
        response_bytes=response_bytes,
    )
    session.add(event)
    await session.commit()
