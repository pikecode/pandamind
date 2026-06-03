"""Process API — render prompt template + call model, return processed result.

For external systems that need model processing with prompt templates.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pandamind.core.auth import require_public_identity
from pandamind.core.middleware import get_current_trace_id
from pandamind.db.models import Prompt as PromptORM
from pandamind.db.session import get_session
from pandamind.providers.base import ChatOptions, Message
from pandamind.providers.registry import get_registry
from pandamind.services.api_keys import (
    ApiIdentity,
    has_model_access,
    has_prompt_access,
    require_scope,
)
from pandamind.services.prompt_engine import PromptEngine
from pandamind.services.usage import record_usage_event

router = APIRouter(prefix="/v1/process", tags=["process"])


@router.post("")
async def process_text(
    data: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    identity: str | ApiIdentity = Depends(require_public_identity),
) -> dict[str, Any]:
    """Render a prompt template and call the model.

    Request body:
        - text: str (required) — input text to process
        - prompt_id: str (required) — prompt template id
        - model: str (optional) — model id to use (defaults to first available)
        - variables: dict (optional) — extra template variables beyond "text"

    Returns:
        - result: str — the model's response
        - model: str — which model was used
        - prompt_id: str — which prompt template was used
        - latency_ms: int — processing time in milliseconds
    """
    text = data.get("text", "")
    prompt_id = data.get("prompt_id", "")
    model_id = data.get("model")
    extra_vars = data.get("variables", {})
    is_external = isinstance(identity, ApiIdentity)

    if not text:
        raise HTTPException(status_code=400, detail="Missing required field: text")
    if not prompt_id:
        raise HTTPException(status_code=400, detail="Missing required field: prompt_id")
    if is_external:
        try:
            require_scope(identity, "process:invoke")
        except ValueError as e:
            raise HTTPException(status_code=403, detail=str(e)) from None
        if not has_prompt_access(identity, prompt_id):
            raise HTTPException(status_code=403, detail="API key is not allowed to use this prompt")

    # Load prompt template
    result = await session.execute(select(PromptORM).where(PromptORM.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_id}' not found")

    # Merge variables: text + extras
    variables = {"text": text, **extra_vars}

    # Validate required variables
    missing = PromptEngine.validate(prompt.system, prompt.user_template, variables)
    if missing:
        raise HTTPException(
            status_code=400,
            detail={"code": "MISSING_TEMPLATE_VARIABLES", "missing": missing},
        )

    # Render prompt
    rendered = PromptEngine.render(prompt.system, prompt.user_template, variables)

    # Resolve model
    registry = get_registry()
    if not model_id:
        # Use first available model
        model_id = _first_available_model(registry)
        if not model_id:
            raise HTTPException(status_code=400, detail="No models configured")
    if is_external and not has_model_access(identity, model_id):
        raise HTTPException(status_code=403, detail="API key is not allowed to use this model")

    provider = registry.resolve(model_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")

    # Build messages
    messages: list[Message] = []
    if rendered.system:
        messages.append(Message(role="system", content=rendered.system))
    if rendered.user:
        messages.append(Message(role="user", content=rendered.user))
    else:
        messages.append(Message(role="user", content=text))

    # Call model
    t0 = time.perf_counter()
    chunks = []
    async for chunk in provider.chat(messages, ChatOptions(temperature=0.7)):
        chunks.append(chunk)
        if chunk.done:
            break
    latency_ms = round((time.perf_counter() - t0) * 1000)

    full_content = "".join(c.content for c in chunks)
    usage = _merge_usage(chunks)

    if is_external:
        await record_usage_event(
            session,
            identity=identity,
            trace_id=get_current_trace_id(),
            endpoint="/v1/process",
            method="POST",
            model_id=model_id,
            prompt_id=prompt_id,
            status_code=200,
            usage=usage,
            provider_latency_ms=latency_ms,
            total_latency_ms=latency_ms,
        )

    return {
        "result": full_content,
        "model": model_id,
        "prompt_id": prompt_id,
        "latency_ms": latency_ms,
    }


def _first_available_model(registry: Any) -> str | None:
    """Return the first available model id from the registry."""
    # Access internal dict for now; registry could expose this later
    providers = getattr(registry, "_providers", {})
    if providers:
        return next(iter(providers.keys()))
    return None


def _merge_usage(chunks: list[Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for chunk in chunks:
        if not getattr(chunk, "usage", None):
            continue
        merged["prompt_tokens"] += chunk.usage.get("prompt_tokens", 0)
        merged["completion_tokens"] += chunk.usage.get("completion_tokens", 0)
        merged["total_tokens"] += chunk.usage.get("total_tokens", 0)
    return merged
