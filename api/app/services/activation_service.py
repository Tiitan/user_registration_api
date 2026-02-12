import logging
import secrets
from datetime import datetime, timedelta, timezone

import asyncmy
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from api.app.config import get_settings
from api.app.db.transaction import transactional_cursor
from api.app.exceptions.domain import (
    AccountAlreadyActiveError,
    ActivationCodeAttemptsExceededError,
    ActivationCodeExpiredError,
    ActivationCodeMismatchError,
    InvalidCredentialsError,
    UserNotFoundError,
)
from api.app.repositories import ActivationCodeRepository, UserRepository
from api.app.schemas.users import ActivatedUserResponse
from api.app.services.email_dispatcher import EmailDispatcher

logger = logging.getLogger(__name__)


class ActivationService:
    def __init__(self, db_pool: asyncmy.Pool, email_dispatcher: EmailDispatcher) -> None:
        settings = get_settings()
        self._db_pool = db_pool
        self._email_dispatcher = email_dispatcher
        self._activation_code_ttl_seconds = settings.activation_code_ttl_seconds
        self._activation_code_max_attempts = settings.activation_code_max_attempts
        self._password_hasher = PasswordHasher()
        self._user_repository = UserRepository()
        self._activation_code_repository = ActivationCodeRepository()

    async def activate_user(self, *, email: str, password: str, code: str) -> ActivatedUserResponse:
        logger.info("Starting activation transaction for email=%s", email)
        resend_info: tuple[int, int, str, str] | None = None
        deferred_error: Exception | None = None
        user_id: int | None = None
        user_email: str | None = None

        try:
            async with transactional_cursor(self._db_pool) as cursor:
                user_row = await self._user_repository.get_by_email_for_update(cursor=cursor, email=email)
                if user_row is None:
                    raise UserNotFoundError()
                user_id = user_row.id
                user_email = user_row.email
                self._verify_password(password=password, password_hash=user_row.password_hash)

                if user_row.status == "ACTIVE":
                    raise AccountAlreadyActiveError()

                code_row = await self._activation_code_repository.get_latest_for_update(cursor=cursor, user_id=user_id)
                if code_row is None:
                    raise ActivationCodeMismatchError()

                activation_code_id = code_row.id
                attempt_count = code_row.attempt_count
                if attempt_count >= self._activation_code_max_attempts:
                    raise ActivationCodeAttemptsExceededError()

                if self._is_code_expired(code_row.sent_at):
                    new_code = f"{secrets.randbelow(10_000):04d}"
                    new_activation_code_id = await self._activation_code_repository.create_code(
                        cursor=cursor,
                        user_id=user_id,
                        code=new_code,
                    )
                    resend_info = (user_id, new_activation_code_id, user_email, new_code)
                    deferred_error = ActivationCodeExpiredError()

                if deferred_error is None and code_row.code != code:
                    await self._activation_code_repository.increment_attempt_count(
                        cursor=cursor,
                        activation_code_id=activation_code_id,
                    )
                    if attempt_count + 1 >= self._activation_code_max_attempts:
                        deferred_error = ActivationCodeAttemptsExceededError()
                    else:
                        deferred_error = ActivationCodeMismatchError()

                if deferred_error is None:
                    await self._activation_code_repository.mark_used(cursor=cursor, activation_code_id=activation_code_id)
                    await self._user_repository.mark_user_as_active(cursor=cursor, user_id=user_id)
        except Exception as error:
            logger.exception("Activation transaction failed for email=%s, error:%s", email, error)
            raise

        if resend_info is not None:
            user_id, new_activation_code_id, user_email, new_code = resend_info
            self._email_dispatcher.dispatch_activation_email(
                user_id=user_id,
                activation_code_id=new_activation_code_id,
                recipient_email=user_email,
                code=new_code,
            )
        if deferred_error is not None:
            raise deferred_error

        if user_id is None or user_email is None:
            raise RuntimeError("Activation finished without resolved user identity")
        logger.info("Activation committed for email=%s user_id=%s", email, user_id)
        return ActivatedUserResponse(id=user_id, email=user_email, status="ACTIVE")

    def _verify_password(self, *, password: str, password_hash: str) -> None:
        try:
            self._password_hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError):
            raise InvalidCredentialsError()

    def _is_code_expired(self, sent_at: datetime | None) -> bool:
        if sent_at is None:
            return False
        sent_at_utc = self._as_utc(sent_at)
        now_utc = self._utc_now()
        return now_utc > sent_at_utc + timedelta(seconds=self._activation_code_ttl_seconds)

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _utc_now(self) -> datetime:
        return datetime.now(timezone.utc)
