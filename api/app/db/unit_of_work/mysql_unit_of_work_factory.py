"""MySQL-backed unit of work factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncmy

from api.app.db.transaction import transactional_cursor
from api.app.repositories import ActivationCodeRepository, UserRepository
from api.app.unit_of_work import ActivationPort, CleanupPort, DispatchPort, RegistrationPort

from .activation_port_adapter import ActivationPortAdapter
from .cleanup_port_adapter import CleanupPortAdapter
from .dispatch_port_adapter import DispatchPortAdapter
from .registration_port_adapter import RegistrationPortAdapter


class MySqlUnitOfWorkFactory:
    """Create transactional MySQL-backed ports for service operations."""

    def __init__(self, db_pool: asyncmy.Pool, *, user_repository: UserRepository | None = None, activation_code_repository: ActivationCodeRepository | None = None) -> None:
        """Initialize with pool and optional repository overrides."""
        self._db_pool = db_pool
        self._user_repository = user_repository or UserRepository()
        self._activation_code_repository = activation_code_repository or ActivationCodeRepository()

    @asynccontextmanager
    async def registration(self) -> AsyncIterator[RegistrationPort]:
        """Yield registration port in one transaction."""
        async with transactional_cursor(self._db_pool) as cursor:
            yield RegistrationPortAdapter(cursor=cursor, user_repository=self._user_repository, activation_code_repository=self._activation_code_repository)

    @asynccontextmanager
    async def activation(self) -> AsyncIterator[ActivationPort]:
        """Yield activation port in one transaction."""
        async with transactional_cursor(self._db_pool) as cursor:
            yield ActivationPortAdapter(cursor=cursor, user_repository=self._user_repository, activation_code_repository=self._activation_code_repository)

    @asynccontextmanager
    async def dispatch(self) -> AsyncIterator[DispatchPort]:
        """Yield dispatch port in one transaction."""
        async with transactional_cursor(self._db_pool) as cursor:
            yield DispatchPortAdapter(cursor=cursor, activation_code_repository=self._activation_code_repository)

    @asynccontextmanager
    async def cleanup(self) -> AsyncIterator[CleanupPort]:
        """Yield cleanup port in one transaction."""
        async with transactional_cursor(self._db_pool) as cursor:
            yield CleanupPortAdapter(cursor=cursor, user_repository=self._user_repository, activation_code_repository=self._activation_code_repository)
