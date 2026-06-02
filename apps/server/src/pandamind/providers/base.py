"""Base Provider interface.

All model providers (Ollama, OpenAI-compatible, etc.) implement this interface.
The Model Router dispatches requests based on the model id without caring
which concrete provider is handling the stream.
"""
from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ChatChunk:
    content: str
    done: bool = False
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ChatOptions:
    temperature: float = 0.7
    max_tokens: int | None = None
    top_p: float | None = None
    stop: list[str] | None = None


@dataclass(frozen=True, slots=True)
class Message:
    role: str  # user / assistant / system
    content: str


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    status: str  # reachable | unreachable | unknown
    message: str | None = None
    latency_ms: float | None = None
    checked_at: str = ""  # iso timestamp


@dataclass(frozen=True, slots=True)
class ModelInfo:
    id: str
    name: str
    size: int | None = None
    modified_at: str | None = None


class BaseProvider(ABC):
    """Abstract base for all model providers."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")
        self.api_key = api_key
        self._abort_map: dict[str, Any] = {}  # stream_id -> abort handle

    @abstractmethod
    async def chat(self, messages: list[Message], options: ChatOptions) -> AsyncIterator[ChatChunk]:
        """Yield ChatChunk until done=True."""
        ...

    def abort(self, stream_id: str) -> None:
        """Cancel a running stream by its stream_id."""
        handle = self._abort_map.pop(stream_id, None)
        if handle is not None:
            with contextlib.suppress(Exception):
                handle()

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Return current provider health."""
        ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Return models available on this provider."""
        ...

    def _register_abort(self, stream_id: str, handle: Any) -> None:
        self._abort_map[stream_id] = handle

    def _unregister_abort(self, stream_id: str) -> None:
        self._abort_map.pop(stream_id, None)
