import json
import secrets

import asyncmy
from argon2 import PasswordHasher
from asyncmy.cursors import DictCursor

from api.app.exceptions.domain import EmailAlreadyExistsError
from api.app.schemas.users import UserResponse


class RegistrationService:
    def __init__(self, db_pool: asyncmy.Pool) -> None:
        self._db_pool = db_pool
        self.password_hasher = PasswordHasher()

    async def register_user(self, *, email: str, password: str) -> UserResponse:
        password_hash = self.password_hasher.hash(password)
        code = f"{secrets.randbelow(10_000):04d}"

        async with self._db_pool.acquire() as connection:
            try:
                await connection.begin()
                async with connection.cursor(DictCursor) as cursor:
                    await cursor.execute(
                        """
                        SELECT id, status
                        FROM users
                        WHERE email = %s
                        FOR UPDATE
                        """,
                        (email,),
                    )
                    existing_user = await cursor.fetchone()

                    if existing_user is None:
                        await cursor.execute(
                            """
                            INSERT INTO users (email, password_hash, status)
                            VALUES (%s, %s, 'PENDING')
                            """,
                            (email, password_hash),
                        )
                        user_id = int(cursor.lastrowid)
                    else:
                        user_id = int(existing_user["id"])
                        if existing_user["status"] == "ACTIVE":
                            raise EmailAlreadyExistsError()
                        await cursor.execute(
                            """
                            UPDATE users
                            SET password_hash = %s
                            WHERE id = %s AND status = 'PENDING'
                            """,
                            (password_hash, user_id),
                        )

                    await cursor.execute(
                        """
                        INSERT INTO activation_codes (user_id, code)
                        VALUES (%s, %s)
                        """,
                        (user_id, code),
                    )
                    activation_code_id = int(cursor.lastrowid)

                    outbox_payload = json.dumps(
                        {
                            "user_id": user_id,
                            "email": email,
                            "activation_code_id": activation_code_id,
                            "code": code,
                        }
                    )

                    await cursor.execute(
                        """
                        INSERT INTO outbox_events (event_type, payload, status, next_attempt_at)
                        VALUES ('activation_code_email_requested', CAST(%s AS JSON), 'PENDING', CURRENT_TIMESTAMP(6))
                        """,
                        (outbox_payload,),
                    )
                await connection.commit()
            except Exception:
                await connection.rollback()
                raise

        return UserResponse(id=user_id, email=email, status="PENDING")
