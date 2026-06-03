"""Application configuration loaded from environment variables.

All settings are loaded via pydantic-settings. The Settings instance is
created once at module import and reused throughout the app (singleton).
"""
from __future__ import annotations

import base64
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # --- Database ---
    database_url: str = Field(
        default="postgresql://pandamind:pandamind@localhost:5432/pandamind",
        description="Async PostgreSQL DSN (use postgresql+asyncpg:// scheme)",
    )

    # --- Security ---
    # ENCRYPTION_KEY is base64-encoded 32 random bytes used for AES-256-GCM.
    # Generate with: python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
    encryption_key: str = Field(
        ...,
        min_length=44,  # base64 of 32 bytes = 44 chars exactly
        max_length=44,
        description="Base64-encoded 32-byte key for AES-256-GCM API key encryption",
    )

    # --- CORS ---
    # Comma-separated list of allowed origins
    allowed_origins: str = "http://localhost:5173,http://localhost:8000"

    # --- Auth ---
    auth_disabled: bool = False
    auth_username: str = "admin"
    auth_password: str = "changeme"
    jwt_secret: str = ""

    # --- Pre-configured API Keys (comma-separated list of key=scope pairs) ---
    # Format: "key1:scope1,scope2;key2:scope3"
    # Example: "pmk_live_xxx:chat:invoke,process:invoke"
    api_keys: str = ""

    @field_validator("database_url")
    @classmethod
    def _ensure_asyncpg_scheme(cls, v: str) -> str:
        """SQLAlchemy async requires explicit asyncpg driver in the DSN."""
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @field_validator("encryption_key")
    @classmethod
    def _validate_encryption_key(cls, v: str) -> str:
        """Decode base64 and ensure the resulting key is exactly 32 bytes."""
        try:
            decoded = base64.b64decode(v, validate=True)
        except Exception as e:
            raise ValueError(
                "ENCRYPTION_KEY is not valid base64. "
                "Generate one with: "
                "python -c \"import os, base64; print(base64.b64encode(os.urandom(32)).decode())\""
            ) from e
        if len(decoded) != 32:
            raise ValueError(
                f"ENCRYPTION_KEY must decode to exactly 32 bytes, got {len(decoded)} bytes. "
                "Generate one with: "
                "python -c \"import os, base64; print(base64.b64encode(os.urandom(32)).decode())\""
            )
        return v

    @property
    def encryption_key_bytes(self) -> bytes:
        """Decoded 32-byte key for direct use with cryptography library."""
        return base64.b64decode(self.encryption_key)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def effective_jwt_secret(self) -> str:
        """Return the JWT secret; falls back to encryption_key when unset."""
        return self.jwt_secret if self.jwt_secret else self.encryption_key

    @property
    def pre_configured_api_keys(self) -> dict[str, list[str]]:
        """Parse API_KEYS env var into dict of key -> scopes."""
        result: dict[str, list[str]] = {}
        if not self.api_keys:
            return result
        for entry in self.api_keys.split(";"):
            entry = entry.strip()
            if not entry:
                continue
            if "=" in entry:
                key, scopes_str = entry.split("=", 1)
                scopes = [s.strip() for s in scopes_str.split(",") if s.strip()]
                result[key.strip()] = scopes
            else:
                result[entry] = []
        return result


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton settings instance."""
    return Settings()  # type: ignore[call-arg]
