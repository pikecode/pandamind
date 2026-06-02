"""JWT authentication dependency.

Behaviour controlled by ``AUTH_DISABLED`` env var (via Settings):
- ``True``  → every request is treated as authenticated (no-op dependency)
- ``False`` → real JWT validation via ``pyjwt``

Tokens are issued via ``POST /v1/auth/login`` with a username/password
pair configured in env vars ``AUTH_USERNAME`` / ``AUTH_PASSWORD``.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from pandamind.core.config import get_settings
from pandamind.db.session import get_session
from pandamind.services.api_keys import ApiIdentity, authenticate_api_key

_BEARER = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_token(username: str, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT. ``secret`` and ``lifetime`` come from settings."""
    settings = get_settings()
    expire = datetime.now(UTC) + (expires_delta or timedelta(hours=24))
    payload: dict[str, Any] = {"sub": username, "exp": expire}
    return jwt.encode(payload, settings.effective_jwt_secret, algorithm="HS256")


def _decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.effective_jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token") from None


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def require_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(_BEARER),
) -> str:
    """Return the authenticated username. Bypassed when ``AUTH_DISABLED=true``."""
    settings = get_settings()
    if settings.auth_disabled:
        return "anonymous"

    if creds is None or creds.credentials == "":
        raise HTTPException(status_code=401, detail="Missing bearer token")

    payload = _decode_token(creds.credentials)
    username: str | None = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return username


async def require_public_identity(
    creds: HTTPAuthorizationCredentials | None = Depends(_BEARER),
    session: AsyncSession = Depends(get_session),
) -> str | ApiIdentity:
    """Authenticate public API calls with API key, falling back to admin JWT.

    External systems should use PandaMind API keys. The JWT fallback keeps the
    existing Web UI and local smoke tests working while Public API matures.
    """
    settings = get_settings()
    if settings.auth_disabled:
        return "anonymous"

    if creds is None or creds.credentials == "":
        raise HTTPException(status_code=401, detail="Missing bearer token")

    identity = await authenticate_api_key(session, creds.credentials)
    if identity is not None:
        return identity

    payload = _decode_token(creds.credentials)
    username: str | None = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return username


def require_external_api_key(identity: str | ApiIdentity) -> ApiIdentity:
    """Return API identity, rejecting admin JWT identities for external-only paths."""
    if isinstance(identity, ApiIdentity):
        return identity
    raise HTTPException(status_code=403, detail="External API key required")
