"""API routers registration."""
from __future__ import annotations

from fastapi import APIRouter

from pandamind.api.api_clients import router as api_clients_router
from pandamind.api.auth import router as auth_router
from pandamind.api.chat import router as chat_router
from pandamind.api.models import router as models_router
from pandamind.api.process import router as process_router
from pandamind.api.prompts import router as prompts_router
from pandamind.api.public import router as public_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(api_clients_router)
api_router.include_router(models_router)
api_router.include_router(chat_router)
api_router.include_router(prompts_router)
api_router.include_router(process_router)
api_router.include_router(public_router)
