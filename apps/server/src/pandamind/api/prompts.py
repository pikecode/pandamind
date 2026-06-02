"""Prompt template API routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pandamind.core.auth import require_auth
from pandamind.core.ids import generate_id
from pandamind.db.models import Prompt as PromptORM
from pandamind.db.models import PromptVersion
from pandamind.db.session import get_session
from pandamind.services.prompt_engine import PromptEngine

router = APIRouter(prefix="/v1/prompts", tags=["prompts"])


def _serialize_prompt(prompt: PromptORM) -> dict[str, Any]:
    return {
        "id": prompt.id,
        "name": prompt.name,
        "description": prompt.description,
        "system": prompt.system,
        "user_template": prompt.user_template,
        "variables": prompt.variables,
        "tags": prompt.tags,
        "version": prompt.version,
        "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
        "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None,
    }


@router.get("", response_model=list[dict[str, Any]])
async def list_prompts(
    tag: str | None = None,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> list[dict[str, Any]]:
    query = select(PromptORM)
    if tag:
        query = query.where(PromptORM.tags.contains([tag]))
    if search:
        query = query.where(PromptORM.name.ilike(f"%{search}%"))
    result = await session.execute(query)
    prompts = result.scalars().all()
    return [_serialize_prompt(p) for p in prompts]


@router.post("", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_prompt(
    data: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    prompt_id = generate_id()
    prompt = PromptORM(
        id=prompt_id,
        name=data["name"],
        description=data.get("description"),
        system=data.get("system"),
        user_template=data.get("user_template"),
        variables=data.get("variables", []),
        tags=data.get("tags", []),
        version=1,
    )
    session.add(prompt)
    await session.commit()
    await session.refresh(prompt)
    return _serialize_prompt(prompt)


@router.get("/{prompt_id}", response_model=dict[str, Any])
async def get_prompt(
    prompt_id: str,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    result = await session.execute(select(PromptORM).where(PromptORM.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _serialize_prompt(prompt)


@router.put("/{prompt_id}", response_model=dict[str, Any])
async def update_prompt(
    prompt_id: str,
    data: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    result = await session.execute(select(PromptORM).where(PromptORM.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # Save version snapshot before update
    version_snapshot = _serialize_prompt(prompt)
    version_snapshot["updated_at"] = str(prompt.updated_at) if prompt.updated_at else None

    version = PromptVersion(
        prompt_id=prompt_id,
        version=prompt.version,
        snapshot=version_snapshot,
    )
    session.add(version)

    # Update prompt
    if "name" in data:
        prompt.name = data["name"]
    if "description" in data:
        prompt.description = data.get("description")
    if "system" in data:
        prompt.system = data.get("system")
    if "user_template" in data:
        prompt.user_template = data.get("user_template")
    if "variables" in data:
        prompt.variables = data["variables"]
    if "tags" in data:
        prompt.tags = data["tags"]
    prompt.version += 1

    await session.commit()
    await session.refresh(prompt)
    return _serialize_prompt(prompt)


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(
    prompt_id: str,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> None:
    result = await session.execute(select(PromptORM).where(PromptORM.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    await session.delete(prompt)
    await session.commit()


@router.post("/{prompt_id}/render")
async def render_prompt(
    prompt_id: str,
    data: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    result = await session.execute(select(PromptORM).where(PromptORM.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    variables = data.get("variables", {})
    missing = PromptEngine.validate(prompt.system, prompt.user_template, variables)
    if missing:
        raise HTTPException(
            status_code=400,
            detail={"code": "MISSING_TEMPLATE_VARIABLES", "missing": missing},
        )

    rendered = PromptEngine.render(prompt.system, prompt.user_template, variables)
    return {
        "system": rendered.system,
        "user": rendered.user,
        "variables": rendered.variables,
    }


@router.get("/{prompt_id}/versions")
async def list_versions(
    prompt_id: str,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> list[dict[str, Any]]:
    result = await session.execute(
        select(PromptVersion).where(PromptVersion.prompt_id == prompt_id).order_by(PromptVersion.version.desc())
    )
    versions = result.scalars().all()
    return [
        {
            "version": v.version,
            "snapshot": v.snapshot,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in versions
    ]


@router.post("/{prompt_id}/rollback/{version}")
async def rollback_version(
    prompt_id: str,
    version: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    result = await session.execute(
        select(PromptVersion).where(
            PromptVersion.prompt_id == prompt_id,
            PromptVersion.version == version,
        )
    )
    pv = result.scalar_one_or_none()
    if not pv:
        raise HTTPException(status_code=404, detail="Version not found")

    prompt_result = await session.execute(select(PromptORM).where(PromptORM.id == prompt_id))
    prompt = prompt_result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # Save current as new version
    current_snapshot = _serialize_prompt(prompt)
    current_version = PromptVersion(
        prompt_id=prompt_id,
        version=prompt.version,
        snapshot=current_snapshot,
    )
    session.add(current_version)

    # Restore from snapshot
    snapshot = pv.snapshot
    prompt.name = snapshot["name"]
    prompt.description = snapshot.get("description")
    prompt.system = snapshot.get("system")
    prompt.user_template = snapshot.get("user_template")
    prompt.variables = snapshot.get("variables", [])
    prompt.tags = snapshot.get("tags", [])
    prompt.version += 1

    await session.commit()
    await session.refresh(prompt)
    return _serialize_prompt(prompt)
