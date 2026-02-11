import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from pydantic_core import PydanticCustomError

PASSWORD_HAS_DIGIT = re.compile(r"\d")
PASSWORD_HAS_LETTER = re.compile(r"[A-Za-z]")


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": "StrongPass123",
            }
        }
    )

    email: EmailStr = Field(description="User email address")
    password: str = Field(
        description="Password with at least 8 characters, including one letter and one digit"
    )

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if len(value) < 8:
            raise PydanticCustomError(
                "password_too_short",
                "Password must be at least 8 characters long",
            )
        if not PASSWORD_HAS_LETTER.search(value) or not PASSWORD_HAS_DIGIT.search(value):
            raise PydanticCustomError(
                "password_not_complex_enough",
                "Password must contain at least one letter and one digit",
            )
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 123,
                "email": "user@example.com",
                "status": "PENDING",
            }
        }
    )

    id: int = Field(description="Unique user identifier")
    email: EmailStr = Field(description="Registered user email")
    status: Literal["PENDING"] = Field(description="Current user status")
