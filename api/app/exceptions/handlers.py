from collections.abc import Awaitable, Callable
import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from api.app.exceptions.domain import (
    AccountAlreadyActiveError,
    ActivationCodeAttemptsExceededError,
    ActivationCodeExpiredError,
    ActivationCodeMismatchError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    UserNotFoundError,
)

logger = logging.getLogger(__name__)


def _build_error_response(*, status_code: int, error: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": {"error": error, "message": message, "details": None}}, headers=headers)


def _make_domain_handler(*, status_code: int, error: str, message: str, headers: dict[str, str] | None = None) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def _handler(request: Request, __: Exception) -> JSONResponse:
        logger.warning(
            "Handled domain exception",
            extra={
                "event": "api_error",
                "error_code": error,
                "status_code": status_code,
                "http_method": request.method,
                "path": request.url.path,
            },
        )
        return _build_error_response(status_code=status_code, error=error, message=message, headers=headers)
    return _handler


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        EmailAlreadyExistsError,
        _make_domain_handler(
            status_code=status.HTTP_409_CONFLICT,
            error="email_already_exists",
            message="Email is already registered as an active account",
        ),
    )
    app.add_exception_handler(
        InvalidCredentialsError,
        _make_domain_handler(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error="invalid_credentials",
            message="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        ),
    )
    app.add_exception_handler(
        UserNotFoundError,
        _make_domain_handler(
            status_code=status.HTTP_404_NOT_FOUND,
            error="user_not_found",
            message="User not found",
        ),
    )
    app.add_exception_handler(
        AccountAlreadyActiveError,
        _make_domain_handler(
            status_code=status.HTTP_409_CONFLICT,
            error="account_already_active",
            message="Account already active",
        ),
    )
    app.add_exception_handler(
        ActivationCodeExpiredError,
        _make_domain_handler(
            status_code=status.HTTP_410_GONE,
            error="activation_code_expired",
            message="Activation code expired",
        ),
    )
    app.add_exception_handler(
        ActivationCodeMismatchError,
        _make_domain_handler(
            status_code=status.HTTP_400_BAD_REQUEST,
            error="activation_code_mismatch",
            message="Invalid activation code",
        ),
    )
    app.add_exception_handler(
        ActivationCodeAttemptsExceededError,
        _make_domain_handler(
            status_code=status.HTTP_400_BAD_REQUEST,
            error="activation_code_attempts_exceeded",
            message="Activation code attempts exceeded",
        ),
    )
