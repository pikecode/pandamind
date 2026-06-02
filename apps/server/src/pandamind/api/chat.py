"""Chat API — OpenAI-compatible /v1/chat/completions with SSE streaming.

Usage tracking: each conversation records token usage (from provider chunks)
and provider latency. GET /v1/chat/stats aggregates by model and date.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pandamind.core.auth import require_auth, require_public_identity
from pandamind.core.ids import generate_id
from pandamind.core.middleware import get_current_trace_id
from pandamind.db.models import Conversation
from pandamind.db.session import AsyncSessionLocal, get_session
from pandamind.providers.base import ChatChunk, ChatOptions, Message
from pandamind.providers.registry import get_registry
from pandamind.services.api_keys import ApiIdentity, has_model_access, require_scope
from pandamind.services.usage import record_usage_event

router = APIRouter(prefix="/v1/chat", tags=["chat"])

# In-memory map: stream_id -> asyncio.Event for cancellation
_stream_events: dict[str, asyncio.Event] = {}


# ── Chat completions ────────────────────────────────────────────────────────

@router.post("/completions")
async def chat_completions(
    request: Request,
    session: AsyncSession = Depends(get_session),
    identity: str | ApiIdentity = Depends(require_public_identity),
) -> StreamingResponse:
    body = await request.json()
    model_id = body.get("model")
    messages_raw = body.get("messages", [])
    stream = body.get("stream", True)
    is_external = isinstance(identity, ApiIdentity)
    trace_id = get_current_trace_id()

    if is_external:
        try:
            require_scope(identity, "chat:invoke")
        except ValueError as e:
            raise HTTPException(status_code=403, detail=str(e)) from None
        if not has_model_access(identity, model_id):
            raise HTTPException(status_code=403, detail="API key is not allowed to use this model")

    registry = get_registry()
    provider = registry.resolve(model_id)
    if not provider:
        error = {"error": {"code": "MODEL_NOT_FOUND", "message": f"Model '{model_id}' not found"}}
        if not stream:
            return error
        return StreamingResponse(
            _error_stream("MODEL_NOT_FOUND", f"Model '{model_id}' not found"),
            media_type="text/event-stream",
        )

    messages = [Message(role=m["role"], content=m["content"]) for m in messages_raw]

    options = ChatOptions(
        temperature=body.get("temperature", 0.7),
        max_tokens=body.get("max_tokens"),
        top_p=body.get("top_p"),
        stop=body.get("stop"),
    )

    stream_id = generate_id()
    t0 = time.perf_counter()

    if not stream:
        chunks: list[ChatChunk] = []
        async for chunk in provider.chat(messages, options):
            chunks.append(chunk)
        latency_ms = round((time.perf_counter() - t0) * 1000)
        full_content = "".join(c.content for c in chunks)
        usage = _merge_usage(chunks)
        await _save_conversation(stream_id, model_id, messages_raw, full_content, usage, latency_ms)
        if is_external:
            await record_usage_event(
                session,
                identity=identity,
                trace_id=trace_id,
                endpoint="/v1/chat/completions",
                method="POST",
                model_id=model_id,
                status_code=200,
                usage=usage,
                provider_latency_ms=latency_ms,
                total_latency_ms=latency_ms,
            )
        return {
            "id": stream_id,
            "object": "chat.completion",
            "model": model_id,
            "choices": [{"message": {"role": "assistant", "content": full_content}, "finish_reason": "stop"}],
            "usage": usage,
        }

    # Register abort event
    abort_event = asyncio.Event()
    _stream_events[stream_id] = abort_event

    async def _stream() -> Any:
        collected: list[ChatChunk] = []
        try:
            async for chunk in provider.chat(messages, options):
                if abort_event.is_set():
                    break
                collected.append(chunk)
                data = {
                    "id": stream_id,
                    "object": "chat.completion.chunk",
                    "model": model_id,
                    "choices": [{"delta": {"content": chunk.content}, "finish_reason": chunk.finish_reason}],
                }
                if chunk.usage:
                    data["usage"] = chunk.usage
                yield f"data: {json.dumps(data)}\n\n"
                if chunk.done:
                    yield "data: [DONE]\n\n"
                    break
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            _stream_events.pop(stream_id, None)
            latency_ms = round((time.perf_counter() - t0) * 1000)
            usage = _merge_usage(collected)
            full_text = "".join(c.content for c in collected)
            await _save_conversation(stream_id, model_id, messages_raw, full_text, usage, latency_ms)
            if is_external:
                async with AsyncSessionLocal() as usage_session:
                    await record_usage_event(
                        usage_session,
                        identity=identity,
                        trace_id=trace_id,
                        endpoint="/v1/chat/completions",
                        method="POST",
                        model_id=model_id,
                        status_code=200,
                        usage=usage,
                        provider_latency_ms=latency_ms,
                        total_latency_ms=latency_ms,
                    )

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "X-Stream-Id": stream_id,
            "X-Trace-Id": trace_id,
            "Cache-Control": "no-cache",
        },
    )


# ── Abort ───────────────────────────────────────────────────────────────────

@router.delete("/{stream_id}")
async def abort_stream(stream_id: str) -> dict[str, str]:
    event = _stream_events.get(stream_id)
    if event and not event.is_set():
        event.set()
        return {"status": "cancelled"}
    return {"status": "not_found_or_already_done"}


# ── Usage stats ─────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(Conversation)
            .where(Conversation.usage.isnot(None))
            .where(Conversation.usage != {})
        )
    ).scalars().all()

    by_model: dict[str, dict[str, Any]] = {}
    by_date: dict[str, dict[str, Any]] = {}

    for conv in rows:
        usage: dict[str, Any] = conv.usage or {}
        total_tokens = usage.get("total_tokens", 0)
        model = conv.model_name or conv.model_id

        if model not in by_model:
            by_model[model] = {"conversations": 0, "total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}
        by_model[model]["conversations"] += 1
        by_model[model]["total_tokens"] += total_tokens
        by_model[model]["prompt_tokens"] += usage.get("prompt_tokens", 0)
        by_model[model]["completion_tokens"] += usage.get("completion_tokens", 0)

        if conv.created_at:
            day = conv.created_at.strftime("%Y-%m-%d")
            if day not in by_date:
                by_date[day] = {"conversations": 0, "total_tokens": 0}
            by_date[day]["conversations"] += 1
            by_date[day]["total_tokens"] += total_tokens

    return {
        "by_model": by_model,
        "by_date": dict(sorted(by_date.items(), reverse=True)[:30]),
        "total_conversations": len(rows),
    }


# ── Internal helpers ────────────────────────────────────────────────────────

def _merge_usage(chunks: list[ChatChunk]) -> dict[str, Any]:
    merged: dict[str, Any] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for c in chunks:
        if not c.usage:
            continue
        merged["prompt_tokens"] += c.usage.get("prompt_tokens", 0)
        merged["completion_tokens"] += c.usage.get("completion_tokens", 0)
        merged["total_tokens"] += c.usage.get("total_tokens", 0)
    return merged


async def _save_conversation(
    stream_id: str,
    model_id: str,
    messages_raw: list[dict[str, Any]],
    assistant_text: str,
    usage: dict[str, Any],
    latency_ms: int,
) -> None:
    async with AsyncSessionLocal() as session:
        conv = Conversation(
            id=stream_id,
            model_id=model_id,
            model_name=model_id,
            messages=messages_raw + [{"role": "assistant", "content": assistant_text}],
            usage=usage,
            provider_latency_ms=latency_ms,
        )
        session.add(conv)
        await session.commit()


def _error_stream(code: str, message: str) -> Any:
    async def _gen():
        yield f"data: {json.dumps({'error': {'code': code, 'message': message}})}\n\n"
    return _gen()
