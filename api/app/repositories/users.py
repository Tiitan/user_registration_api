"""User persistence models and queries."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UserRecord:
    """User row projection used by the service layer."""

    id: int
    email: str
    password_hash: str
    status: str


class UserRepository:
    """Data access methods for `users` records."""

    async def get_by_email_for_update(self, *, cursor: Any, email: str) -> UserRecord | None:
        """Load a user by email and lock the row for update."""
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
        """Create a pending user and return its identifier."""
        await cursor.execute(
            "INSERT INTO users (email, password_hash, status) VALUES (%s, %s, 'PENDING')",
            (email, password_hash),
        )
        return int(cursor.lastrowid)

    async def update_pending_password(self, *, cursor: Any, user_id: int, password_hash: str) -> None:
        """Update password hash when the user is still pending."""
        await cursor.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s AND status = 'PENDING'",
            (password_hash, user_id),
        )

    async def mark_user_as_active(self, *, cursor: Any, user_id: int) -> None:
        """Mark a pending user as active and set activation timestamp."""
        await cursor.execute(
            "UPDATE users SET status = 'ACTIVE', activated_at = CURRENT_TIMESTAMP(6) WHERE id = %s AND status = 'PENDING'",
            (user_id,),
        )

    async def count_stale_pending_users(self, *, cursor: Any, retention_hours: int) -> int:
        """Count pending users older than the configured retention window."""
        await cursor.execute(
            "SELECT COUNT(*) AS count "
            "FROM users "
            "WHERE status = 'PENDING' "
            "AND created_at < (CURRENT_TIMESTAMP(6) - INTERVAL %s HOUR)",
            (retention_hours,),
        )
        row = await cursor.fetchone()
        if row is None:
            return 0
        return int(row["count"])

    async def delete_stale_pending_users(self, *, cursor: Any, retention_hours: int) -> int:
        """Delete pending users older than the configured retention window."""
        await cursor.execute(
            "DELETE FROM users "
            "WHERE status = 'PENDING' "
            "AND created_at < (CURRENT_TIMESTAMP(6) - INTERVAL %s HOUR)",
            (retention_hours,),
        )
        return int(cursor.rowcount)
