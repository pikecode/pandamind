"""Ollama provider implementation."""
from __future__ import annotations

import json
from typing import Any

import httpx

from pandamind.providers.base import (
    BaseProvider,
    ChatChunk,
    ChatOptions,
    Message,
    ModelInfo,
    ProviderHealth,
)


class OllamaProvider(BaseProvider):
    """Provider for local Ollama HTTP API."""

    async def chat(self, messages: list[Message], options: ChatOptions) -> Any:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model_name,  # set by registry
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {
                "temperature": options.temperature,
                **({"num_predict": options.max_tokens} if options.max_tokens else {}),
            },
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client, client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("done"):
                        yield ChatChunk(
                            content="",
                            done=True,
                            finish_reason="stop",
                        )
                        return
                    if "message" in data and data["message"].get("content"):
                        yield ChatChunk(content=data["message"]["content"], done=False)

    async def health_check(self) -> ProviderHealth:
        import time as _time
        start = _time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                r.raise_for_status()
            return ProviderHealth(
                status="reachable",
                latency_ms=round((_time.perf_counter() - start) * 1000, 2),
                checked_at=__import__("datetime").datetime.now(__import__("zoneinfo").ZoneInfo("UTC")).isoformat(),
            )
        except Exception as e:
            return ProviderHealth(
                status="unreachable",
                message=str(e),
                latency_ms=round((_time.perf_counter() - start) * 1000, 2),
                checked_at=__import__("datetime").datetime.now(__import__("zoneinfo").ZoneInfo("UTC")).isoformat(),
            )

    async def list_models(self) -> list[ModelInfo]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            r = await client.get(f"{self.base_url}/api/tags")
            r.raise_for_status()
            data = r.json()
        return [
            ModelInfo(
                id=m["name"],
                name=m["name"],
                size=m.get("size"),
                modified_at=m.get("modified_at"),
            )
            for m in data.get("models", [])
        ]
