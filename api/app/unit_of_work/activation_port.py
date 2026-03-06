"""Activation transaction persistence port."""

from typing import Protocol

from api.app.repositories import ActivationCodeRecord, UserRecord


class ActivationPort(Protocol):
    """Persistence operations needed by activation flow."""

    async def get_user_by_email_for_update(self, *, email: str) -> UserRecord | None:
        """Load and lock user by email."""
        ...

    async def get_latest_activation_code_for_update(self, *, user_id: int) -> ActivationCodeRecord | None:
        """Load and lock latest activation code."""
        ...

    async def create_activation_code(self, *, user_id: int, code: str) -> int:
        """Create activation code and return identifier."""
        ...

    async def increment_activation_attempt_count(self, *, activation_code_id: int) -> None:
        """Increment failed activation attempt count."""
        ...

    async def mark_activation_code_used(self, *, activation_code_id: int) -> None:
        """Mark activation code as used."""
        ...

    async def mark_user_as_active(self, *, user_id: int) -> None:
        """Mark user account as active."""
        ...
