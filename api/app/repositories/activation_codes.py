"""Activation code persistence models and queries."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ActivationCodeRecord:
    """Activation code row projection used by services."""

    id: int
    user_id: int
    code: str
    sent_at: datetime | None
    attempt_count: int


class ActivationCodeRepository:
    """Data access methods for `activation_codes` records."""

    async def create_code(self, *, cursor: Any, user_id: int, code: str) -> int:
        """Create an activation code and return its identifier."""
        await cursor.execute("INSERT INTO activation_codes (user_id, code) VALUES (%s, %s)", (user_id, code))
        return int(cursor.lastrowid)

    async def get_latest_for_update(self, *, cursor: Any, user_id: int) -> ActivationCodeRecord | None:
        """Load and lock the most recent activation code for a user."""
        await cursor.execute(
            "SELECT id, user_id, code, sent_at, attempt_count "
            "FROM activation_codes "
            "WHERE user_id = %s "
            "ORDER BY created_at DESC, id DESC "
            "LIMIT 1 FOR UPDATE",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return ActivationCodeRecord(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            code=str(row["code"]),
            sent_at=row["sent_at"],
            attempt_count=int(row["attempt_count"]),
        )

    async def increment_attempt_count(self, *, cursor: Any, activation_code_id: int) -> None:
        """Increment failed attempt count for an activation code."""
        await cursor.execute(
            "UPDATE activation_codes SET attempt_count = attempt_count + 1 WHERE id = %s",
            (activation_code_id,),
        )

    async def mark_used(self, *, cursor: Any, activation_code_id: int) -> None:
        """Set `used_at` when the code has been consumed."""
        await cursor.execute(
            "UPDATE activation_codes SET used_at = CURRENT_TIMESTAMP(6) WHERE id = %s AND used_at IS NULL",
            (activation_code_id,),
        )

    async def mark_sent(self, *, cursor: Any, activation_code_id: int) -> None:
        """Set `sent_at` when delivery succeeds."""
        await cursor.execute(
            "UPDATE activation_codes SET sent_at = CURRENT_TIMESTAMP(6) WHERE id = %s AND sent_at IS NULL",
            (activation_code_id,),
        )

    async def count_undelivered(self, *, cursor: Any) -> int:
        """Count activation codes still waiting for delivery."""
        await cursor.execute("SELECT COUNT(*) AS undelivered_count FROM activation_codes WHERE sent_at IS NULL")
        row = await cursor.fetchone()
        if row is None:
            return 0
        return int(row["undelivered_count"])

    async def count_stale_activation_codes(self, *, cursor: Any, retention_hours: int) -> int:
        """Count activation codes older than the configured retention window."""
        await cursor.execute(
            "SELECT COUNT(*) AS count "
            "FROM activation_codes "
            "WHERE created_at < (CURRENT_TIMESTAMP(6) - INTERVAL %s HOUR)",
            (retention_hours,),
        )
        row = await cursor.fetchone()
        if row is None:
            return 0
        return int(row["count"])

    async def delete_stale_activation_codes(self, *, cursor: Any, retention_hours: int) -> int:
        """Delete activation codes older than the configured retention window."""
        await cursor.execute(
            "DELETE FROM activation_codes "
            "WHERE created_at < (CURRENT_TIMESTAMP(6) - INTERVAL %s HOUR)",
            (retention_hours,),
        )
        return int(cursor.rowcount)
