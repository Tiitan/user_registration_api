"""Domain exceptions and exception handler registration."""

from .domain import (
    AccountAlreadyActiveError,
    ActivationCodeAttemptsExceededError,
    ActivationCodeExpiredError,
    ActivationCodeMismatchError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    UserNotFoundError,
)
from .handlers import register_exception_handlers

__all__ = [
    "AccountAlreadyActiveError",
    "ActivationCodeAttemptsExceededError",
    "ActivationCodeExpiredError",
    "ActivationCodeMismatchError",
    "EmailAlreadyExistsError",
    "InvalidCredentialsError",
    "UserNotFoundError",
    "register_exception_handlers",
]
