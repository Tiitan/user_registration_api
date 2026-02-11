import logging

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from api.app.dependencies import get_activation_service, get_registration_service
from api.app.exceptions.domain import (
    AccountAlreadyActiveError,
    ActivationCodeAttemptsExceededError,
    ActivationCodeExpiredError,
    ActivationCodeMismatchError,
    ActivationCodeNotDeliveredError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    UserNotFoundError,
)
from api.app.schemas.errors import ErrorResponse
from api.app.schemas.users import ActivateUserRequest, ActivatedUserResponse, CreateUserRequest, UserResponse
from api.app.services.activation_service import ActivationService
from api.app.services.registration_service import RegistrationService

router = APIRouter(prefix="/v1/users", tags=["users"])
logger = logging.getLogger(__name__)
http_basic = HTTPBasic(auto_error=False)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user",
    description="Create or reset a pending user account and schedule activation code delivery.",
    responses={
        201: {
            "description": "User created or pending account reset",
            "content": {"application/json": {"example": {"id": 123, "email": "user@example.com", "status": "PENDING"}}},
        },
        409: {
            "description": "Email already belongs to an active account",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "error": "email_already_exists",
                            "message": "Email is already registered as an active account",
                            "details": None,
                        }
                    }
                }
            },
        },
        422: {"description": "Payload validation error"},
    },
)
async def create_user(payload: CreateUserRequest, service: RegistrationService = Depends(get_registration_service)) -> UserResponse:
    logger.info("POST /v1/users requested for email=%s", payload.email)
    try:
        user = await service.register_user(email=payload.email, password=payload.password)
        logger.info("POST /v1/users succeeded for email=%s user_id=%s", payload.email, user.id)
        return user
    except EmailAlreadyExistsError as exc:
        logger.warning("POST /v1/users conflict for email=%s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "email_already_exists",
                "message": "Email is already registered as an active account",
                "details": None,
            },
        ) from exc


@router.post(
    "/activate",
    response_model=ActivatedUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Activate a user",
    description=(
        "Activate account using Basic Auth credentials and a 4-digit code. "
        "Activation requires a delivered code (`sent_at` set) and a non-expired 60-second window."
    ),
    responses={
        200: {
            "description": "Account activated",
            "content": {"application/json": {"example": {"id": 123, "email": "user@example.com", "status": "ACTIVE"}}},
        },
        400: {
            "description": "Invalid code, code not delivered, or attempts exceeded",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "examples": {
                        "mismatch": {
                            "summary": "Code mismatch",
                            "value": {"detail": {"error": "activation_code_mismatch", "message": "Invalid activation code", "details": None}},
                        },
                        "not_delivered": {
                            "summary": "Code not delivered yet",
                            "value": {
                                "detail": {
                                    "error": "activation_code_not_delivered",
                                    "message": "Activation code has not been delivered yet",
                                    "details": None,
                                }
                            },
                        },
                        "attempts_exceeded": {
                            "summary": "Attempts exceeded",
                            "value": {
                                "detail": {
                                    "error": "activation_code_attempts_exceeded",
                                    "message": "Activation code attempts exceeded",
                                    "details": None,
                                }
                            },
                        },
                    }
                }
            },
        },
        401: {
            "description": "Invalid or missing Basic Auth credentials",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "error": "invalid_credentials",
                            "message": "Invalid credentials",
                            "details": None,
                        }
                    }
                }
            },
        },
        404: {
            "description": "User not found",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {"detail": {"error": "user_not_found", "message": "User not found", "details": None}}
                }
            },
        },
        409: {
            "description": "Account already active",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "error": "account_already_active",
                            "message": "Account already active",
                            "details": None,
                        }
                    }
                }
            },
        },
        410: {
            "description": "Activation code expired",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "error": "activation_code_expired",
                            "message": "Activation code expired",
                            "details": None,
                        }
                    }
                }
            },
        },
        422: {"description": "Payload validation error"},
    },
)
async def activate_user(payload: ActivateUserRequest, credentials: HTTPBasicCredentials | None = Security(http_basic), service: ActivationService = Depends(get_activation_service)) -> ActivatedUserResponse:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials", "message": "Invalid credentials", "details": None},
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.info("POST /v1/users/activate requested for email=%s", credentials.username)
    try:
        user = await service.activate_user(email=credentials.username, password=credentials.password, code=payload.code)
        logger.info("POST /v1/users/activate succeeded for email=%s user_id=%s", user.email, user.id)
        return user
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials", "message": "Invalid credentials", "details": None},
            headers={"WWW-Authenticate": "Basic"},
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "user_not_found", "message": "User not found", "details": None},
        ) from exc
    except AccountAlreadyActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "account_already_active", "message": "Account already active", "details": None},
        ) from exc
    except ActivationCodeNotDeliveredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "activation_code_not_delivered", "message": "Activation code has not been delivered yet", "details": None},
        ) from exc
    except ActivationCodeExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"error": "activation_code_expired", "message": "Activation code expired", "details": None},
        ) from exc
    except ActivationCodeMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "activation_code_mismatch", "message": "Invalid activation code", "details": None},
        ) from exc
    except ActivationCodeAttemptsExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "activation_code_attempts_exceeded",
                "message": "Activation code attempts exceeded",
                "details": None,
            },
        ) from exc
