"""Unit tests for PromptEngine."""
from __future__ import annotations

from pandamind.services.prompt_engine import PromptEngine


def test_extract_variables_simple():
    assert sorted(PromptEngine.extract_variables("Hello {{name}}, welcome to {{place}}")) == [
        "name",
        "place",
    ]


def test_extract_variables_with_defaults():
    assert sorted(PromptEngine.extract_variables("{{lang|python}} and {{code}}")) == [
        "code",
        "lang",
    ]


def test_extract_variables_none_input():
    assert PromptEngine.extract_variables(None) == []


def test_extract_variables_no_vars():
    assert PromptEngine.extract_variables("plain text with no vars") == []


def test_render_simple():
    result = PromptEngine.render("You are {{role}}", "Translate {{text}} to {{lang}}", {"role": "tutor", "text": "hello", "lang": "French"})
    assert result.system == "You are tutor"
    assert result.user == "Translate hello to French"
    assert result.variables == {"role": "tutor", "text": "hello", "lang": "French"}


def test_render_with_default():
    result = PromptEngine.render("{{style|casual}}", "Write about {{topic}}", {"topic": "AI"})
    assert result.system == "casual"


def test_render_value_overrides_default():
    result = PromptEngine.render("{{style|casual}}", None, {"style": "formal"})
    assert result.system == "formal"


def test_render_none_templates():
    result = PromptEngine.render(None, None, {"x": "1"})
    assert result.system is None
    assert result.user is None


def test_validate_all_present():
    missing = PromptEngine.validate("{{a}}", "{{b}}", {"a": "1", "b": "2"})
    assert missing == []


def test_validate_missing_required():
    missing = PromptEngine.validate("{{a}} {{b}}", None, {"a": "1"})
    assert missing == ["b"]


def test_validate_default_satisfies():
    missing = PromptEngine.validate("{{a|fallback}}", None, {})
    assert missing == []


def test_validate_empty_string_is_missing():
    missing = PromptEngine.validate("{{x}}", None, {"x": ""})
    assert missing == ["x"]
