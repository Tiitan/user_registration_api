from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UserRecord:
    id: int
    email: str
    password_hash: str
    status: str


class UserRepository:
    async def get_by_email_for_update(self, *, cursor: Any, email: str) -> UserRecord | None:
        await cursor.execute("SELECT id, email, password_hash, status FROM users WHERE email = %s FOR UPDATE", (email,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return UserRecord(
            id=int(row["id"]),
            email=str(row["email"]),
            password_hash=str(row["password_hash"]),
            status=str(row["status"]),
        )

    async def create_pending_user(self, *, cursor: Any, email: str, password_hash: str) -> int:
        await cursor.execute(
            "INSERT INTO users (email, password_hash, status) VALUES (%s, %s, 'PENDING')",
            (email, password_hash),
        )
        return int(cursor.lastrowid)

    async def update_pending_password(self, *, cursor: Any, user_id: int, password_hash: str) -> None:
        await cursor.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s AND status = 'PENDING'",
            (password_hash, user_id),
        )

    async def mark_user_as_active(self, *, cursor: Any, user_id: int) -> None:
        await cursor.execute(
            "UPDATE users SET status = 'ACTIVE', activated_at = CURRENT_TIMESTAMP(6) WHERE id = %s AND status = 'PENDING'",
            (user_id,),
        )
