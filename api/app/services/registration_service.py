import logging
import secrets

import asyncmy
from argon2 import PasswordHasher
from asyncmy.cursors import DictCursor

from api.app.exceptions.domain import EmailAlreadyExistsError
from api.app.schemas.users import UserResponse
from api.app.services.email_dispatcher import EmailDispatcher

logger = logging.getLogger(__name__)


class RegistrationService:
    def __init__(self, db_pool: asyncmy.Pool, email_dispatcher: EmailDispatcher) -> None:
        self._db_pool = db_pool
        self._email_dispatcher = email_dispatcher
        self.password_hasher = PasswordHasher()

    async def register_user(self, *, email: str, password: str) -> UserResponse:
        logger.info("Starting registration transaction for email=%s", email)
        password_hash = self.password_hasher.hash(password)
        code = f"{secrets.randbelow(10_000):04d}"

        async with self._db_pool.acquire() as connection:
            try:
                await connection.begin()
                async with connection.cursor(DictCursor) as cursor:
                    await cursor.execute("SELECT id, status FROM users WHERE email = %s FOR UPDATE", (email,))
                    existing_user = await cursor.fetchone()

                    if existing_user is None:
                        await cursor.execute("INSERT INTO users (email, password_hash, status) VALUES (%s, %s, 'PENDING')",
                            (email, password_hash))
                        user_id = int(cursor.lastrowid)
                    else:
                        user_id = int(existing_user["id"])
                        if existing_user["status"] == "ACTIVE":
                            logger.warning("Registration rejected: email=%s is already active", email)
                            raise EmailAlreadyExistsError()
                        await cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s AND status = 'PENDING'",
                            (password_hash, user_id))

                    await cursor.execute("INSERT INTO activation_codes (user_id, code) VALUES (%s, %s)", (user_id, code))
                    activation_code_id = int(cursor.lastrowid)
                await connection.commit()
                logger.info("Registration committed for email=%s user_id=%s", email, user_id)
            except Exception:
                logger.exception("Registration transaction failed for email=%s", email)
                await connection.rollback()
                raise

        self._email_dispatcher.dispatch_activation_email(
            user_id=user_id,
            activation_code_id=activation_code_id,
            recipient_email=email,
            code=code,
        )

        return UserResponse(id=user_id, email=email, status="PENDING")
