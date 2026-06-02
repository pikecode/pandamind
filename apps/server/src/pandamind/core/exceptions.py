"""Unified error envelope and exception types.

All HTTP error responses use the shape::

    {
        "code": "PROVIDER_UNAVAILABLE",
        "message": "Ollama provider is not reachable",
        "details": { ... },          # optional, never includes secrets
        "traceId": "abc123xyz"       # always present
    }
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


class ApiError(HTTPException):
    """Application-level error with stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail={"code": code, "message": message, "details": details})
        self.code = code
        self.message = message
        self.details = details


class ProviderUnavailable(ApiError):
    def __init__(self, provider: str, message: str | None = None) -> None:
        super().__init__(
            code="PROVIDER_UNAVAILABLE",
            message=message or f"Provider '{provider}' is not reachable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"provider": provider},
        )


class ModelNotFound(ApiError):
    def __init__(self, model_id: str) -> None:
        super().__init__(
            code="MODEL_NOT_FOUND",
            message=f"Model '{model_id}' not found",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"model_id": model_id},
        )


class ValidationFailed(ApiError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class InternalError(ApiError):
    def __init__(self, message: str = "Internal server error") -> None:
        super().__init__(
            code="INTERNAL_ERROR",
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
