"""MySQL registration port adapter."""

from asyncmy.cursors import DictCursor

from api.app.repositories import ActivationCodeRepository, UserRecord, UserRepository


class RegistrationPortAdapter:
    """Registration port implementation bound to one transaction cursor."""

    def __init__(self, *, cursor: DictCursor, user_repository: UserRepository, activation_code_repository: ActivationCodeRepository) -> None:
        """Store cursor-scoped repository dependencies."""
        self._cursor = cursor
        self._user_repository = user_repository
        self._activation_code_repository = activation_code_repository

    async def get_user_by_email_for_update(self, *, email: str) -> UserRecord | None:
        """Load and lock user by email."""
        return await self._user_repository.get_by_email_for_update(cursor=self._cursor, email=email)

    async def create_pending_user(self, *, email: str, password_hash: str) -> int:
        """Create pending user."""
        return await self._user_repository.create_pending_user(cursor=self._cursor, email=email, password_hash=password_hash)

    async def update_pending_password(self, *, user_id: int, password_hash: str) -> None:
        """Update pending user password."""
        await self._user_repository.update_pending_password(cursor=self._cursor, user_id=user_id, password_hash=password_hash)

    async def create_activation_code(self, *, user_id: int, code: str) -> int:
        """Create activation code."""
        return await self._activation_code_repository.create_code(cursor=self._cursor, user_id=user_id, code=code)
