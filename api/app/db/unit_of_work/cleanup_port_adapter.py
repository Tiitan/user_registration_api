"""MySQL cleanup port adapter."""

from asyncmy.cursors import DictCursor

from api.app.repositories import ActivationCodeRepository, UserRepository


class CleanupPortAdapter:
    """Cleanup port implementation bound to one transaction cursor."""

    def __init__(self, *, cursor: DictCursor, user_repository: UserRepository, activation_code_repository: ActivationCodeRepository) -> None:
        """Store cursor-scoped repository dependencies."""
        self._cursor = cursor
        self._user_repository = user_repository
        self._activation_code_repository = activation_code_repository

    async def count_stale_pending_users(self, *, retention_hours: int) -> int:
        """Count stale pending users."""
        return await self._user_repository.count_stale_pending_users(cursor=self._cursor, retention_hours=retention_hours)

    async def count_stale_activation_codes(self, *, retention_hours: int) -> int:
        """Count stale activation codes."""
        return await self._activation_code_repository.count_stale_activation_codes(cursor=self._cursor, retention_hours=retention_hours)

    async def delete_stale_pending_users(self, *, retention_hours: int) -> int:
        """Delete stale pending users."""
        return await self._user_repository.delete_stale_pending_users(cursor=self._cursor, retention_hours=retention_hours)

    async def delete_stale_activation_codes(self, *, retention_hours: int) -> int:
        """Delete stale activation codes."""
        return await self._activation_code_repository.delete_stale_activation_codes(cursor=self._cursor, retention_hours=retention_hours)
