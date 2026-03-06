"""MySQL dispatch port adapter."""

from asyncmy.cursors import DictCursor

from api.app.repositories import ActivationCodeRepository


class DispatchPortAdapter:
    """Dispatch port implementation bound to one transaction cursor."""

    def __init__(self, *, cursor: DictCursor, activation_code_repository: ActivationCodeRepository) -> None:
        """Store cursor-scoped repository dependencies."""
        self._cursor = cursor
        self._activation_code_repository = activation_code_repository

    async def mark_activation_code_sent(self, *, activation_code_id: int) -> None:
        """Mark activation code as sent."""
        await self._activation_code_repository.mark_sent(cursor=self._cursor, activation_code_id=activation_code_id)

    async def count_undelivered_activation_codes(self) -> int:
        """Count unsent activation codes."""
        return await self._activation_code_repository.count_undelivered(cursor=self._cursor)
