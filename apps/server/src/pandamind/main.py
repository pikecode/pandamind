"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from pandamind.api import api_router
from pandamind.core.config import get_settings
from pandamind.core.exceptions import ApiError, InternalError
from pandamind.core.logging import configure_logging
from pandamind.core.middleware import TraceIdMiddleware, get_current_trace_id
from pandamind.db.session import engine

settings = get_settings()
configure_logging(settings.log_level)
log = structlog.get_logger("pandamind")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    log.info("startup", env=f"{settings.host}:{settings.port}")
    # Rebuild provider registry from DB
    from pandamind.api.models import _rebuild_registry
    from pandamind.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        await _rebuild_registry(session)
    yield
    log.info("shutdown")
    await engine.dispose()


app = FastAPI(
    title="PandaMind",
    version="0.1.0",
    description="Unified AI model gateway with prompt templates",
    lifespan=lifespan,
)

# Middleware order: TraceId FIRST so every other middleware/handler can read trace id
app.add_middleware(TraceIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Error envelope ---
def _envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "details": details, "traceId": get_current_trace_id()}


@app.exception_handler(ApiError)
async def _api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=_envelope(exc.code, exc.message, exc.details))


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Map common HTTP statuses to stable codes; fall back to generic.
    code_map = {
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
    }
    code = code_map.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(code, message, {"detail": str(exc.detail)} if not isinstance(exc.detail, str) else None),
    )


@app.exception_handler(RequestValidationError)
async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_envelope(
            "VALIDATION_ERROR",
            "Request payload failed validation",
            {"errors": exc.errors()},
        ),
    )


@app.exception_handler(Exception)
async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled", error=str(exc))
    err = InternalError()
    return JSONResponse(status_code=err.status_code, content=_envelope(err.code, err.message))


# --- Health ---
@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


# --- API Routers ---
app.include_router(api_router)
