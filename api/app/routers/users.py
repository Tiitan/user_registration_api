import logging

from fastapi import APIRouter, Depends, HTTPException, status

from api.app.dependencies import get_registration_service
from api.app.exceptions.domain import EmailAlreadyExistsError
from api.app.schemas.users import CreateUserRequest, UserResponse
from api.app.services.registration_service import RegistrationService

router = APIRouter(prefix="/v1/users", tags=["users"])
logger = logging.getLogger(__name__)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user",
    description="Create or reset a pending user account and schedule activation code delivery.",
    responses={
        201: {"description": "User created successfully"},
        409: {
            "description": "Email already belongs to an active account",
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
        422: {"description": "Validation error"},
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
