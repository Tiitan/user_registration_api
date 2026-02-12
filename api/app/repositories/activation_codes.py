from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ActivationCodeRecord:
    id: int
    user_id: int
    code: str
    sent_at: datetime | None
    attempt_count: int


class ActivationCodeRepository:
    async def create_code(self, *, cursor: Any, user_id: int, code: str) -> int:
        await cursor.execute("INSERT INTO activation_codes (user_id, code) VALUES (%s, %s)", (user_id, code))
        return int(cursor.lastrowid)

    async def get_latest_for_update(self, *, cursor: Any, user_id: int) -> ActivationCodeRecord | None:
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
        await cursor.execute(
            "UPDATE activation_codes SET attempt_count = attempt_count + 1 WHERE id = %s",
            (activation_code_id,),
        )

    async def mark_used(self, *, cursor: Any, activation_code_id: int) -> None:
        await cursor.execute(
            "UPDATE activation_codes SET used_at = CURRENT_TIMESTAMP(6) WHERE id = %s AND used_at IS NULL",
            (activation_code_id,),
        )

    async def mark_sent(self, *, cursor: Any, activation_code_id: int) -> None:
        await cursor.execute(
            "UPDATE activation_codes SET sent_at = CURRENT_TIMESTAMP(6) WHERE id = %s AND sent_at IS NULL",
            (activation_code_id,),
        )

    async def count_undelivered(self, *, cursor: Any) -> int:
        await cursor.execute("SELECT COUNT(*) AS undelivered_count FROM activation_codes WHERE sent_at IS NULL")
        row = await cursor.fetchone()
        if row is None:
            return 0
        return int(row["undelivered_count"])
