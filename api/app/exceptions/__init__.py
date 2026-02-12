from api.app.exceptions.domain import (
    AccountAlreadyActiveError,
    ActivationCodeAttemptsExceededError,
    ActivationCodeExpiredError,
    ActivationCodeMismatchError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    UserNotFoundError,
)
from api.app.exceptions.handlers import register_exception_handlers

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
