"""Unit tests for ProviderRegistry."""
from __future__ import annotations

from unittest.mock import MagicMock

from pandamind.providers.registry import ProviderRegistry


def _make_mock_provider(name: str = "mock") -> MagicMock:
    p = MagicMock()
    p.name = name
    return p


def test_register_and_resolve():
    reg = ProviderRegistry()
    p = _make_mock_provider()
    reg.register("model-1", p)
    assert reg.resolve("model-1") is p


def test_resolve_alias():
    reg = ProviderRegistry()
    p = _make_mock_provider()
    reg.register("model-1", p, aliases=["gpt4", "fast"])
    assert reg.resolve("gpt4") is p
    assert reg.resolve("fast") is p


def test_resolve_unknown_returns_none():
    reg = ProviderRegistry()
    assert reg.resolve("nonexistent") is None


def test_alias_does_not_shadow_real_id():
    reg = ProviderRegistry()
    p1 = _make_mock_provider("p1")
    p2 = _make_mock_provider("p2")
    reg.register("model-1", p1, aliases=["alias-x"])
    reg.register("model-2", p2)
    assert reg.resolve("model-1") is p1
    assert reg.resolve("alias-x") is p1
    assert reg.resolve("model-2") is p2


def test_clear():
    reg = ProviderRegistry()
    reg.register("m", _make_mock_provider(), aliases=["a"])
    reg.clear()
    assert reg.resolve("m") is None
    assert reg.resolve("a") is None


def test_get_delegates_to_resolve():
    reg = ProviderRegistry()
    p = _make_mock_provider()
    reg.register("x", p)
    assert reg.get("x") is p
    assert reg.get("nope") is None
