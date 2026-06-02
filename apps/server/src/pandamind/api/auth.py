"""Auth routes — login endpoint returning a JWT."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from pandamind.core.auth import create_token
from pandamind.core.config import get_settings

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/login")
async def login(body: dict) -> dict:
    username = body.get("username", "")
    password = body.get("password", "")
    settings = get_settings()

    if settings.auth_disabled:
        token = create_token("anonymous")
        return {"access_token": token, "token_type": "bearer"}

    if username != settings.auth_username or password != settings.auth_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_token(username)
    return {"access_token": token, "token_type": "bearer"}
