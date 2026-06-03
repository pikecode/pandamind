"""External API key generation, hashing, and verification."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pandamind.core.ids import generate_id
from pandamind.db.models import ApiClient, ApiKey

KEY_PREFIX: Final[str] = "pmk"
PUBLIC_ID_LENGTH: Final[int] = 21
SECRET_BYTES: Final[int] = 32


@dataclass(frozen=True, slots=True)
class GeneratedApiKey:
    plaintext: str
    public_id: str
    key_prefix: str
    key_hash: str
    key_last4: str


@dataclass(frozen=True, slots=True)
class ApiIdentity:
    client_id: str
    api_key_id: str
    scopes: frozenset[str]
    allowed_model_ids: frozenset[str]
    allowed_prompt_ids: frozenset[str]


def generate_api_key(environment: str = "live") -> GeneratedApiKey:
    """Create a new external API key. Plaintext must be shown only once."""
    public_id = generate_id()
    secret = secrets.token_urlsafe(SECRET_BYTES)
    plaintext = f"{KEY_PREFIX}_{environment}_{public_id}_{secret}"
    return GeneratedApiKey(
        plaintext=plaintext,
        public_id=public_id,
        key_prefix=f"{KEY_PREFIX}_{environment}_{public_id}",
        key_hash=hash_api_key(plaintext),
        key_last4=plaintext[-4:],
    )


def hash_api_key(plaintext: str) -> str:
    """Hash an API key for storage and lookup."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def parse_public_id(plaintext: str) -> str | None:
    """Extract public id from pmk_<env>_<public_id>_<secret>."""
    parts = plaintext.split("_", 2)
    if len(parts) != 3 or parts[0] != KEY_PREFIX or not parts[1]:
        return None
    remainder = parts[2]
    if len(remainder) <= PUBLIC_ID_LENGTH or remainder[PUBLIC_ID_LENGTH] != "_":
        return None
    public_id = remainder[:PUBLIC_ID_LENGTH]
    secret = remainder[PUBLIC_ID_LENGTH + 1 :]
    if not public_id or not secret:
        return None
    return public_id


def verify_plaintext(stored_hash: str, plaintext: str) -> bool:
    return hmac.compare_digest(stored_hash, hash_api_key(plaintext))


async def authenticate_api_key(session: AsyncSession, plaintext: str) -> ApiIdentity | None:
    """Return API identity when the key is valid and active."""
    # Check pre-configured API keys first (from env vars)
    from pandamind.core.config import get_settings

    settings = get_settings()
    pre_configured = settings.pre_configured_api_keys
    if plaintext in pre_configured:
        return ApiIdentity(
            client_id="pre-configured",
            api_key_id="pre-configured",
            scopes=frozenset(pre_configured[plaintext]),
            allowed_model_ids=frozenset(),
            allowed_prompt_ids=frozenset(),
        )

    public_id = parse_public_id(plaintext)
    if not public_id:
        return None

    result = await session.execute(
        select(ApiKey, ApiClient)
        .join(ApiClient, ApiClient.id == ApiKey.client_id)
        .where(ApiKey.public_id == public_id)
    )
    row = result.one_or_none()
    if row is None:
        return None

    api_key, client = row
    if api_key.status != "active" or client.status != "active":
        return None
    if api_key.expires_at and api_key.expires_at <= datetime.now(UTC):
        return None
    if not verify_plaintext(api_key.key_hash, plaintext):
        return None

    api_key.last_used_at = datetime.now(UTC)
    await session.commit()

    return ApiIdentity(
        client_id=api_key.client_id,
        api_key_id=api_key.id,
        scopes=frozenset(api_key.scopes or []),
        allowed_model_ids=frozenset(api_key.allowed_model_ids or []),
        allowed_prompt_ids=frozenset(api_key.allowed_prompt_ids or []),
    )


def require_scope(identity: ApiIdentity, scope: str) -> None:
    """Raise ValueError when identity lacks scope."""
    if scope not in identity.scopes:
        raise ValueError(f"Missing required scope: {scope}")


def has_model_access(identity: ApiIdentity, model_id: str | None) -> bool:
    return bool(model_id and model_id in identity.allowed_model_ids)


def has_prompt_access(identity: ApiIdentity, prompt_id: str | None) -> bool:
    return bool(prompt_id and prompt_id in identity.allowed_prompt_ids)
