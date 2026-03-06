"""Service handling account activation transactions."""

import logging
from datetime import datetime, timedelta

from argon2.exceptions import VerificationError, VerifyMismatchError

from api.app.config import get_settings
from api.app.exceptions import (
    AccountAlreadyActiveError,
    ActivationCodeAttemptsExceededError,
    ActivationCodeExpiredError,
    ActivationCodeMismatchError,
    InvalidCredentialsError,
    UserNotFoundError,
)
from api.app.schemas import ActivatedUserResponse
from api.app.security import PASSWORD_HASHER, generate_activation_code
from api.app.services.email_dispatcher import EmailDispatcher
from api.app.unit_of_work import UnitOfWorkFactory

logger = logging.getLogger(__name__)


class ActivationService:
    """Activate pending users using password and activation code."""

    def __init__(self, uow_factory: UnitOfWorkFactory, email_dispatcher: EmailDispatcher) -> None:
        """Initialize service dependencies and activation policy."""
        settings = get_settings()
        self._uow_factory = uow_factory
        self._email_dispatcher = email_dispatcher
        self._activation_code_ttl_seconds = settings.activation_code_ttl_seconds
        self._activation_code_max_attempts = settings.activation_code_max_attempts
        self._password_hasher = PASSWORD_HASHER

    async def activate_user(self, *, email: str, password: str, code: str) -> ActivatedUserResponse:
        """Activate a user or raise a domain error for invalid state. resend new activation code if expired"""
        logger.info("Starting activation transaction for email=%s", email)
        resend_info: tuple[int, int, str, str] | None = None
        deferred_error: Exception | None = None
        user_id: int | None = None
        user_email: str | None = None

        try:
            async with self._uow_factory.activation() as activation_port:
                user_row = await activation_port.get_user_by_email_for_update(email=email)
                if user_row is None:
                    raise UserNotFoundError()
                user_id = user_row.id
                user_email = user_row.email
                self._verify_password(password=password, password_hash=user_row.password_hash)

                if user_row.status == "ACTIVE":
                    raise AccountAlreadyActiveError()

                code_row = await activation_port.get_latest_activation_code_for_update(user_id=user_id)
                if code_row is None:
                    raise ActivationCodeMismatchError()

                activation_code_id = code_row.id
                attempt_count = code_row.attempt_count
                if attempt_count >= self._activation_code_max_attempts:
                    raise ActivationCodeAttemptsExceededError()

                if self._is_code_expired(code_row.sent_at):
                    new_code = generate_activation_code()
                    new_activation_code_id = await activation_port.create_activation_code(user_id=user_id, code=new_code)
                    resend_info = (user_id, new_activation_code_id, user_email, new_code)
                    deferred_error = ActivationCodeExpiredError()

                if deferred_error is None and code_row.code != code:
                    await activation_port.increment_activation_attempt_count(activation_code_id=activation_code_id)
                    if attempt_count + 1 >= self._activation_code_max_attempts:
                        deferred_error = ActivationCodeAttemptsExceededError()
                    else:
                        deferred_error = ActivationCodeMismatchError()

                if deferred_error is None:
                    await activation_port.mark_activation_code_used(activation_code_id=activation_code_id)
                    await activation_port.mark_user_as_active(user_id=user_id)
        except Exception as error:
            logger.exception("Activation transaction failed for email=%s, error:%s", email, error)
            raise

        if resend_info is not None:
            user_id, new_activation_code_id, user_email, new_code = resend_info
            self._email_dispatcher.dispatch_activation_email(user_id=user_id, activation_code_id=new_activation_code_id, recipient_email=user_email, code=new_code)
        if deferred_error is not None:
            raise deferred_error

        if user_id is None or user_email is None:
            raise RuntimeError("Activation finished without resolved user identity")
        logger.info("Activation committed for email=%s user_id=%s", email, user_id)
        return ActivatedUserResponse(id=user_id, email=user_email, status="ACTIVE")

    def _verify_password(self, *, password: str, password_hash: str) -> None:
        """Validate password against the stored hash."""
        try:
            self._password_hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError):
            raise InvalidCredentialsError()

    def _is_code_expired(self, sent_at: datetime | None) -> bool:
        """Return whether the sent timestamp exceeds configured TTL."""
        if sent_at is None:
            return False
        if sent_at.tzinfo is not None:
            raise RuntimeError("Timezone-aware activation sent_at is unsupported; expected naive local datetime")
        return self._now() > sent_at + timedelta(seconds=self._activation_code_ttl_seconds)

    def _now(self) -> datetime:
        """Return current server-local timestamp."""
        return datetime.now()
