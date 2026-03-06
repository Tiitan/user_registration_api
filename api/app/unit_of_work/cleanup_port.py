"""Cleanup transaction persistence port."""

from typing import Protocol


class CleanupPort(Protocol):
    """Persistence operations needed by cleanup script."""

    async def count_stale_pending_users(self, *, retention_hours: int) -> int:
        """Count stale pending users."""
        ...

    async def count_stale_activation_codes(self, *, retention_hours: int) -> int:
        """Count stale activation codes."""
        ...

    async def delete_stale_pending_users(self, *, retention_hours: int) -> int:
        """Delete stale pending users."""
        ...

    async def delete_stale_activation_codes(self, *, retention_hours: int) -> int:
        """Delete stale activation codes."""
        ...
