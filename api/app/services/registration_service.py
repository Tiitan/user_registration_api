"""Service handling user registration transactions."""

import logging

import asyncmy

from api.app.db import transactional_cursor
from api.app.exceptions import EmailAlreadyExistsError
from api.app.repositories import ActivationCodeRepository, UserRepository
from api.app.schemas import UserResponse
from api.app.security import PASSWORD_HASHER, generate_activation_code
from api.app.services.email_dispatcher import EmailDispatcher

logger = logging.getLogger(__name__)


class RegistrationService:
    """Create or reset pending users and enqueue activation delivery."""

    def __init__(self, db_pool: asyncmy.Pool, email_dispatcher: EmailDispatcher) -> None:
        """Initialize service dependencies."""
        self._db_pool = db_pool
        self._email_dispatcher = email_dispatcher
        self._password_hasher = PASSWORD_HASHER
        self._user_repository = UserRepository()
        self._activation_code_repository = ActivationCodeRepository()

    async def register_user(self, *, email: str, password: str) -> UserResponse:
        """Register a user and schedule an activation email."""
        logger.info("Starting registration transaction for email=%s", email)
        password_hash = self._password_hasher.hash(password)
        code = generate_activation_code()

        try:
            async with transactional_cursor(self._db_pool) as cursor:
                existing_user = await self._user_repository.get_by_email_for_update(cursor=cursor, email=email)

                if existing_user is None:
                    user_id = await self._user_repository.create_pending_user(cursor=cursor, email=email, password_hash=password_hash)
                else:
                    user_id = existing_user.id
                    if existing_user.status == "ACTIVE":
                        logger.warning("Registration rejected: email=%s is already active", email)
                        raise EmailAlreadyExistsError()
                    await self._user_repository.update_pending_password(cursor=cursor, user_id=user_id, password_hash=password_hash)

                activation_code_id = await self._activation_code_repository.create_code(cursor=cursor, user_id=user_id, code=code)
            logger.info("Registration committed for email=%s user_id=%s", email, user_id)
        except Exception:
            logger.exception("Registration transaction failed for email=%s", email)
            raise

        self._email_dispatcher.dispatch_activation_email(user_id=user_id, activation_code_id=activation_code_id, recipient_email=email, code=code)

        return UserResponse(id=user_id, email=email, status="PENDING")
