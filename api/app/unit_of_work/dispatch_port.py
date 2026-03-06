"""Email dispatch transaction persistence port."""

from typing import Protocol


class DispatchPort(Protocol):
    """Persistence operations needed by email dispatch flow."""

    async def mark_activation_code_sent(self, *, activation_code_id: int) -> None:
        """Persist sent timestamp."""
        ...

    async def count_undelivered_activation_codes(self) -> int:
        """Count activation codes without sent timestamp."""
        ...
