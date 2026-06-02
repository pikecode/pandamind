"""Unit tests for external API key helpers."""
from __future__ import annotations

from pandamind.services.api_keys import (
    ApiIdentity,
    generate_api_key,
    has_model_access,
    has_prompt_access,
    hash_api_key,
    parse_public_id,
    require_scope,
    verify_plaintext,
)


def test_generate_api_key_shape_and_hash_verification():
    generated = generate_api_key(environment="test")

    assert generated.plaintext.startswith("pmk_test_")
    assert generated.key_prefix.startswith("pmk_test_")
    assert generated.public_id in generated.plaintext
    assert generated.key_last4 == generated.plaintext[-4:]
    assert generated.key_hash == hash_api_key(generated.plaintext)
    assert verify_plaintext(generated.key_hash, generated.plaintext)


def test_parse_public_id():
    generated = generate_api_key()

    assert parse_public_id(generated.plaintext) == generated.public_id
    assert parse_public_id("invalid") is None
    assert parse_public_id("sk_live_abc_secret") is None


def test_parse_public_id_allows_underscores_in_key_parts():
    public_id = "abc_def-0123456789XYZ"
    plaintext = f"pmk_test_{public_id}_secret_with_underscores"

    assert len(public_id) == 21
    assert parse_public_id(plaintext) == public_id


def test_scope_and_resource_helpers():
    identity = ApiIdentity(
        client_id="client-1",
        api_key_id="key-1",
        scopes=frozenset({"chat:invoke"}),
        allowed_model_ids=frozenset({"model-1"}),
        allowed_prompt_ids=frozenset({"prompt-1"}),
    )

    require_scope(identity, "chat:invoke")
    assert has_model_access(identity, "model-1")
    assert not has_model_access(identity, "model-2")
    assert has_prompt_access(identity, "prompt-1")
    assert not has_prompt_access(identity, "prompt-2")


def test_require_scope_rejects_missing_scope():
    identity = ApiIdentity(
        client_id="client-1",
        api_key_id="key-1",
        scopes=frozenset(),
        allowed_model_ids=frozenset(),
        allowed_prompt_ids=frozenset(),
    )

    try:
        require_scope(identity, "chat:invoke")
    except ValueError as exc:
        assert "chat:invoke" in str(exc)
    else:
        raise AssertionError("expected missing scope to raise")
