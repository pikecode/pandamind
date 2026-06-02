"""AES-256-GCM key manager with automatic log redaction."""
from __future__ import annotations

import base64
import logging
import os
from typing import Final

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("pandamind.key_manager")

# PII / secret field names that must never appear in logs
_SECRET_KEYS: Final[frozenset[str]] = frozenset(
    {"apiKey", "api_key", "authorization", "Authorization", "token", "password", "apiKey_enc"}
)


def _scrub(data: dict[str, str]) -> dict[str, str]:
    """Return a copy of data with secret fields replaced by ***REDACTED***."""
    return {k: "***REDACTED***" if k in _SECRET_KEYS else v for k, v in data.items()}


class KeyManager:
    """Encrypts and decrypts API keys using AES-256-GCM.

    The master key is loaded from Settings.encryption_key_bytes (32 bytes).
    Each encrypted value is stored as: base64(nonce + ciphertext + tag).
    """

    def __init__(self, master_key: bytes) -> None:
        if len(master_key) != 32:
            raise ValueError("Master key must be exactly 32 bytes")
        self._cipher = AESGCM(master_key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext, return base64-encoded (nonce + ciphertext)."""
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(nonce, plaintext.encode("utf-8"), None)
        combined = nonce + ciphertext
        return base64.b64encode(combined).decode("ascii")

    def decrypt(self, ciphertext_b64: str) -> str:
        """Decrypt base64-encoded (nonce + ciphertext)."""
        combined = base64.b64decode(ciphertext_b64)
        nonce = combined[:12]
        ciphertext = combined[12:]
        plaintext = self._cipher.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")

    def mask(self, ciphertext_b64: str | None) -> str:
        """Return a masked display string (e.g. sk-...xxxx)."""
        if not ciphertext_b64:
            return ""
        try:
            plain = self.decrypt(ciphertext_b64)
            if len(plain) <= 8:
                return "*" * len(plain)
            return plain[:4] + "..." + plain[-4:]
        except Exception:
            return "***INVALID***"
