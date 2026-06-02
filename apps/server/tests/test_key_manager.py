"""Unit tests for KeyManager (AES-256-GCM encrypt/decrypt/mask)."""
from __future__ import annotations

import os

import pytest

from pandamind.services.key_manager import KeyManager


@pytest.fixture
def km() -> KeyManager:
    return KeyManager(master_key=os.urandom(32))


def test_encrypt_decrypt_roundtrip(km: KeyManager):
    plaintext = "sk-proj-abc123xyz"
    encrypted = km.encrypt(plaintext)
    assert km.decrypt(encrypted) == plaintext


def test_different_nonces_produce_different_ciphertext(km: KeyManager):
    a = km.encrypt("same-value")
    b = km.encrypt("same-value")
    assert a != b  # random nonce


def test_mask_long_key(km: KeyManager):
    enc = km.encrypt("sk-proj-abc123xyz")
    masked = km.mask(enc)
    assert masked.startswith("sk-p")
    assert masked.endswith("xyz")
    assert "..." in masked


def test_mask_short_key(km: KeyManager):
    enc = km.encrypt("ab")
    masked = km.mask(enc)
    assert masked == "**"


def test_mask_none():
    assert KeyManager.__new__(KeyManager).mask(None) == ""  # type: ignore[misc]


def test_mask_invalid_ciphertext(km: KeyManager):
    import base64
    fake = base64.b64encode(b"not-a-valid-ciphertext-xxxxxxxxxxxx").decode()
    assert km.mask(fake) == "***INVALID***"


def test_invalid_master_key_length():
    with pytest.raises(ValueError, match="exactly 32 bytes"):
        KeyManager(master_key=b"short")
