"""MySQL activation port adapter."""

from asyncmy.cursors import DictCursor

from api.app.repositories import ActivationCodeRecord, ActivationCodeRepository, UserRecord, UserRepository


class ActivationPortAdapter:
    """Activation port implementation bound to one transaction cursor."""

    def __init__(self, *, cursor: DictCursor, user_repository: UserRepository, activation_code_repository: ActivationCodeRepository) -> None:
        """Store cursor-scoped repository dependencies."""
        self._cursor = cursor
        self._user_repository = user_repository
        self._activation_code_repository = activation_code_repository

    async def get_user_by_email_for_update(self, *, email: str) -> UserRecord | None:
        """Load and lock user by email."""
        return await self._user_repository.get_by_email_for_update(cursor=self._cursor, email=email)

    async def get_latest_activation_code_for_update(self, *, user_id: int) -> ActivationCodeRecord | None:
        """Load and lock latest activation code for user."""
        return await self._activation_code_repository.get_latest_for_update(cursor=self._cursor, user_id=user_id)

    async def create_activation_code(self, *, user_id: int, code: str) -> int:
        """Create activation code."""
        return await self._activation_code_repository.create_code(cursor=self._cursor, user_id=user_id, code=code)

    async def increment_activation_attempt_count(self, *, activation_code_id: int) -> None:
        """Increment failed attempt count."""
        await self._activation_code_repository.increment_attempt_count(cursor=self._cursor, activation_code_id=activation_code_id)

    async def mark_activation_code_used(self, *, activation_code_id: int) -> None:
        """Mark code as used."""
        await self._activation_code_repository.mark_used(cursor=self._cursor, activation_code_id=activation_code_id)

    async def mark_user_as_active(self, *, user_id: int) -> None:
        """Mark user as active."""
        await self._user_repository.mark_user_as_active(cursor=self._cursor, user_id=user_id)
