"""Registration transaction persistence port."""

from typing import Protocol

from api.app.repositories import UserRecord


class RegistrationPort(Protocol):
    """Persistence operations needed by registration flow."""

    async def get_user_by_email_for_update(self, *, email: str) -> UserRecord | None:
        """Load and lock user by email."""
        ...

    async def create_pending_user(self, *, email: str, password_hash: str) -> int:
        """Create a pending user and return identifier."""
        ...

    async def update_pending_password(self, *, user_id: int, password_hash: str) -> None:
        """Update pending user credentials."""
        ...

    async def create_activation_code(self, *, user_id: int, code: str) -> int:
        """Create activation code and return identifier."""
        ...
