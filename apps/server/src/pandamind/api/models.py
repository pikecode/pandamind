"""Model management API routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pandamind.core.auth import require_auth
from pandamind.core.config import get_settings
from pandamind.core.ids import generate_id
from pandamind.db.models import ModelConfig as ModelConfigORM
from pandamind.db.session import get_session
from pandamind.providers.registry import get_registry, rebuild_registry
from pandamind.services.key_manager import KeyManager

router = APIRouter(prefix="/v1/models", tags=["models"])


def _key_manager() -> KeyManager:
    return KeyManager(get_settings().encryption_key_bytes)


ALLOWED_PROVIDERS = {"ollama", "openai-compatible"}


class ModelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    provider: str
    model: str = Field(min_length=1, max_length=255)
    base_url: str | None = None
    api_key: str | None = None
    default_params: dict[str, Any] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    enabled: bool = True


class ModelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    provider: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1, max_length=255)
    base_url: str | None = None
    api_key: str | None = None
    default_params: dict[str, Any] | None = None
    aliases: list[str] | None = None
    enabled: bool | None = None

    @field_validator("name", "provider", "model", "default_params", "aliases", "enabled")
    @classmethod
    def _reject_null_for_required_fields(cls, v: Any) -> Any:
        """When these fields are explicitly provided, they must not be null."""
        if v is None:
            raise ValueError("This field cannot be set to null; omit it to keep the current value")
        return v


def _serialize(model: ModelConfigORM, *, mask_key: bool = True) -> dict[str, Any]:
    """Serialize a ModelConfig ORM object to a dict, optionally masking the api_key."""
    data = {
        "id": model.id,
        "name": model.name,
        "provider": model.provider,
        "model": model.model,
        "base_url": model.base_url,
        "api_key": None,
        "default_params": model.default_params,
        "aliases": model.aliases,
        "enabled": model.enabled,
        "created_at": model.created_at.isoformat() if model.created_at else None,
        "updated_at": model.updated_at.isoformat() if model.updated_at else None,
    }
    if model.api_key_enc:
        if mask_key:
            data["api_key"] = _key_manager().mask(model.api_key_enc)
        else:
            data["api_key"] = "***ENCRYPTED***"
    return data


@router.get("", response_model=list[dict[str, Any]])
async def list_models(session: AsyncSession = Depends(get_session), _user: str = Depends(require_auth)) -> list[dict[str, Any]]:
    result = await session.execute(select(ModelConfigORM))
    models = result.scalars().all()
    return [_serialize(m) for m in models]


@router.post("", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_model(data: ModelCreate, session: AsyncSession = Depends(get_session), _user: str = Depends(require_auth)) -> dict[str, Any]:
    if data.provider not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {data.provider}. Allowed: {sorted(ALLOWED_PROVIDERS)}")
    km = _key_manager()
    api_key_enc = None
    if data.api_key:
        api_key_enc = km.encrypt(data.api_key)

    model = ModelConfigORM(
        id=generate_id(),
        name=data.name,
        provider=data.provider,
        model=data.model,
        base_url=data.base_url,
        api_key_enc=api_key_enc,
        default_params=data.default_params,
        aliases=data.aliases,
        enabled=data.enabled,
    )
    session.add(model)
    await session.commit()
    await session.refresh(model)

    # Rebuild registry with new config
    await _rebuild_registry(session)
    return _serialize(model)


@router.get("/{model_id}", response_model=dict[str, Any])
async def get_model(model_id: str, session: AsyncSession = Depends(get_session), _user: str = Depends(require_auth)) -> dict[str, Any]:
    result = await session.execute(select(ModelConfigORM).where(ModelConfigORM.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return _serialize(model)


@router.put("/{model_id}", response_model=dict[str, Any])
async def update_model(model_id: str, data: ModelUpdate, session: AsyncSession = Depends(get_session), _user: str = Depends(require_auth)) -> dict[str, Any]:
    result = await session.execute(select(ModelConfigORM).where(ModelConfigORM.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    if data.provider is not None and data.provider not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {data.provider}. Allowed: {sorted(ALLOWED_PROVIDERS)}")

    km = _key_manager()
    updates = data.model_dump(exclude_unset=True)

    if "name" in updates:
        model.name = data.name
    if "provider" in updates:
        model.provider = data.provider
    if "model" in updates:
        model.model = data.model
    if "base_url" in updates:
        model.base_url = data.base_url
    if "api_key" in updates:
        model.api_key_enc = km.encrypt(data.api_key) if data.api_key else None
    if "default_params" in updates:
        model.default_params = data.default_params
    if "aliases" in updates:
        model.aliases = data.aliases
    if "enabled" in updates:
        model.enabled = data.enabled

    await session.commit()
    await session.refresh(model)

    # Rebuild registry
    await _rebuild_registry(session)
    return _serialize(model)


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(model_id: str, session: AsyncSession = Depends(get_session), _user: str = Depends(require_auth)) -> None:
    result = await session.execute(select(ModelConfigORM).where(ModelConfigORM.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    await session.delete(model)
    await session.commit()
    await _rebuild_registry(session)


@router.get("/{model_id}/ping")
async def ping_model(model_id: str, session: AsyncSession = Depends(get_session), _user: str = Depends(require_auth)) -> dict[str, Any]:
    registry = get_registry()
    health = await registry.health_check(model_id)
    return {
        "model_id": model_id,
        "health": {
            "status": health.status,
            "message": health.message,
            "latency_ms": health.latency_ms,
            "checked_at": health.checked_at,
        },
    }


@router.get("/{model_id}/list")
async def list_provider_models(model_id: str, session: AsyncSession = Depends(get_session), _user: str = Depends(require_auth)) -> list[dict[str, Any]]:
    registry = get_registry()
    models = await registry.list_models(model_id)
    return [{"id": m.id, "name": m.name, "size": m.size, "modified_at": m.modified_at} for m in models]


async def _rebuild_registry(session: AsyncSession) -> None:
    """Load all enabled model configs from DB and rebuild the provider registry."""
    result = await session.execute(select(ModelConfigORM).where(ModelConfigORM.enabled.is_(True)))
    models = result.scalars().all()
    km = _key_manager()
    configs = []
    for m in models:
        configs.append({
            "id": m.id,
            "provider": m.provider,
            "model": m.model,
            "base_url": m.base_url,
            "api_key_enc": km.decrypt(m.api_key_enc) if m.api_key_enc else None,
            "aliases": m.aliases,
        })
    rebuild_registry(configs)
