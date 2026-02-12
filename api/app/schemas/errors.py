"""Error response schemas used across endpoints."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    """Machine- and human-readable error metadata."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "activation_code_expired",
                "message": "Activation code expired",
                "details": None,
            }
        }
    )

    error: str = Field(description="Stable machine-readable error code")
    message: str = Field(description="Human-readable error message")
    details: Any | None = Field(default=None, description="Optional structured details")


class ErrorResponse(BaseModel):
    """Top-level API error response body."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": {
                    "error": "activation_code_expired",
                    "message": "Activation code expired",
                    "details": None,
                }
            }
        }
    )

    detail: ErrorDetail
