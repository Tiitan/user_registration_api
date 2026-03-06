"""Unit tests for registration cleanup script using cleanup ports."""

import asyncio
from contextlib import asynccontextmanager

from scripts import registration_cleanup


class _FakePool:
    """Minimal pool stub used by cleanup script."""

    def __init__(self) -> None:
        """Initialize close tracking."""
        self.closed = False
        self.wait_closed_calls = 0

    def close(self) -> None:
        """Mark pool as closed."""
        self.closed = True

    async def wait_closed(self) -> None:
        """Track wait_closed invocation."""
        self.wait_closed_calls += 1


class _FakeCleanupPort:
    """In-memory cleanup port fake with configurable row counts."""

    def __init__(self, *, pending_users_count: int, stale_codes_count: int, pending_users_deleted: int, stale_codes_deleted: int) -> None:
        """Configure dry-run and delete mode return values."""
        self.pending_users_count = pending_users_count
        self.stale_codes_count = stale_codes_count
        self.pending_users_deleted = pending_users_deleted
        self.stale_codes_deleted = stale_codes_deleted
        self.count_calls = 0
        self.delete_calls = 0

    async def count_stale_pending_users(self, *, retention_hours: int) -> int:
        """Return configured stale pending user count."""
        self.count_calls += 1
        return self.pending_users_count

    async def count_stale_activation_codes(self, *, retention_hours: int) -> int:
        """Return configured stale activation code count."""
        self.count_calls += 1
        return self.stale_codes_count

    async def delete_stale_pending_users(self, *, retention_hours: int) -> int:
        """Return configured deleted pending users count."""
        self.delete_calls += 1
        return self.pending_users_deleted

    async def delete_stale_activation_codes(self, *, retention_hours: int) -> int:
        """Return configured deleted stale codes count."""
        self.delete_calls += 1
        return self.stale_codes_deleted


class _FakeUnitOfWorkFactory:
    """Return a prebuilt cleanup port inside an async context."""

    def __init__(self, cleanup_port: _FakeCleanupPort) -> None:
        """Store fake cleanup port."""
        self._cleanup_port = cleanup_port

    @asynccontextmanager
    async def cleanup(self):
        """Yield fake cleanup port."""
        yield self._cleanup_port


def test_run_cleanup_dry_run_uses_count_methods(monkeypatch) -> None:
    """Dry-run returns count values and does not delete rows."""
    fake_pool = _FakePool()
    fake_port = _FakeCleanupPort(pending_users_count=3, stale_codes_count=8, pending_users_deleted=0, stale_codes_deleted=0)
    fake_factory = _FakeUnitOfWorkFactory(fake_port)
    async def _create_pool():
        return fake_pool

    monkeypatch.setattr(registration_cleanup, "create_mysql_pool_with_retry", _create_pool)
    monkeypatch.setattr(registration_cleanup, "MySqlUnitOfWorkFactory", lambda pool: fake_factory)

    result = asyncio.run(
        registration_cleanup.run_cleanup(
            pending_user_retention_hours=24,
            activation_code_retention_hours=1,
            dry_run=True,
        )
    )

    assert result.pending_users == 3
    assert result.stale_activation_codes == 8
    assert result.dry_run is True
    assert fake_port.count_calls == 2
    assert fake_port.delete_calls == 0
    assert fake_pool.closed is True
    assert fake_pool.wait_closed_calls == 1


def test_run_cleanup_execute_uses_delete_methods(monkeypatch) -> None:
    """Execution mode returns deleted row counts."""
    fake_pool = _FakePool()
    fake_port = _FakeCleanupPort(pending_users_count=0, stale_codes_count=0, pending_users_deleted=5, stale_codes_deleted=11)
    fake_factory = _FakeUnitOfWorkFactory(fake_port)
    async def _create_pool():
        return fake_pool

    monkeypatch.setattr(registration_cleanup, "create_mysql_pool_with_retry", _create_pool)
    monkeypatch.setattr(registration_cleanup, "MySqlUnitOfWorkFactory", lambda pool: fake_factory)

    result = asyncio.run(
        registration_cleanup.run_cleanup(
            pending_user_retention_hours=24,
            activation_code_retention_hours=1,
            dry_run=False,
        )
    )

    assert result.pending_users == 5
    assert result.stale_activation_codes == 11
    assert result.dry_run is False
    assert fake_port.count_calls == 0
    assert fake_port.delete_calls == 2
    assert fake_pool.closed is True
    assert fake_pool.wait_closed_calls == 1
