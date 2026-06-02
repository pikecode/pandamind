"""Provider registry: loads model configs from DB, instantiates providers,
and dispatches chat requests to the correct provider.

Registry is rebuilt from DB snapshot on every mutation (no hot-swap)."""
from __future__ import annotations

from typing import Any

from pandamind.providers.base import BaseProvider, ModelInfo, ProviderHealth
from pandamind.providers.ollama import OllamaProvider
from pandamind.providers.openai_compatible import OpenAICompatibleProvider


class ProviderRegistry:
    """Holds all active provider instances. Rebuilt on config change."""

    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}
        self._aliases: dict[str, str] = {}  # alias -> model_id

    def register(self, model_id: str, provider: BaseProvider, aliases: list[str] | None = None) -> None:
        self._providers[model_id] = provider
        for alias in (aliases or []):
            self._aliases[alias] = model_id

    def resolve(self, model_id: str) -> BaseProvider | None:
        """Resolve a model id or alias to its provider instance."""
        if model_id in self._providers:
            return self._providers[model_id]
        target = self._aliases.get(model_id)
        if target and target in self._providers:
            return self._providers[target]
        return None

    def get(self, model_id: str) -> BaseProvider | None:
        return self.resolve(model_id)

    async def health_check(self, model_id: str) -> ProviderHealth:
        provider = self.resolve(model_id)
        if not provider:
            return ProviderHealth(status="unknown", message=f"Model {model_id} not registered")
        return await provider.health_check()

    async def list_models(self, model_id: str) -> list[ModelInfo]:
        provider = self.resolve(model_id)
        if not provider:
            return []
        return await provider.list_models()

    def clear(self) -> None:
        self._providers.clear()
        self._aliases.clear()


# Global singleton — rebuilt on every config change.
_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def rebuild_registry(configs: list[dict[str, Any]]) -> ProviderRegistry:
    """Rebuild registry from a list of model config dicts.

    configs: list of dicts with keys id, provider, model, base_url, api_key_enc, aliases
    """
    global _registry
    new_registry = ProviderRegistry()
    for cfg in configs:
        provider_type = cfg.get("provider")
        base_url = cfg.get("base_url")
        api_key = cfg.get("api_key_enc")
        if provider_type == "ollama":
            p = OllamaProvider(base_url=base_url, api_key=api_key)
        elif provider_type == "openai-compatible":
            p = OpenAICompatibleProvider(base_url=base_url, api_key=api_key)
        else:
            continue
        p.model_name = cfg.get("model", cfg["id"])
        new_registry.register(cfg["id"], p, aliases=cfg.get("aliases", []))
    _registry = new_registry
    return new_registry
