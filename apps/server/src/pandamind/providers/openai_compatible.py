"""OpenAI-compatible provider (covers OpenAI, DeepSeek, Groq, etc.)."""
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


class OpenAICompatibleProvider(BaseProvider):
    """Provider for any OpenAI-compatible HTTP API."""

    async def chat(self, messages: list[Message], options: ChatOptions) -> Any:
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "temperature": options.temperature,
        }
        if options.max_tokens is not None:
            payload["max_tokens"] = options.max_tokens
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client, client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[len("data: "):]
                    if data_str.strip() == "[DONE]":
                        yield ChatChunk(content="", done=True, finish_reason="stop")
                        return
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    choices = data.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    finish = choices[0].get("finish_reason")
                    if finish:
                        yield ChatChunk(content="", done=True, finish_reason=finish)
                        return
                    if content:
                        yield ChatChunk(content=content, done=False)

    async def health_check(self) -> ProviderHealth:
        import time as _time
        start = _time.perf_counter()
        try:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                r = await client.get(f"{self.base_url}/v1/models", headers=headers)
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
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            r = await client.get(f"{self.base_url}/v1/models", headers=headers)
            r.raise_for_status()
            data = r.json()
        return [
            ModelInfo(id=m["id"], name=m.get("id", m["id"]))
            for m in data.get("data", [])
        ]
