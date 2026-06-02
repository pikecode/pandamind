"""ID generation utility. All primary keys are 21-char URL-safe nanoids."""
from __future__ import annotations

from nanoid import generate as _nano_generate

_ALPHABET = "_-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_SIZE = 21


def generate_id() -> str:
    """Generate a new 21-character URL-safe nanoid."""
    return _nano_generate(_ALPHABET, _SIZE)
