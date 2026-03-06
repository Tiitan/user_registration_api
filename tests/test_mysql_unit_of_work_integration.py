"""Integration tests for MySQL unit of work transaction behavior."""

import asyncio

import pytest

from api.app.db import MySqlUnitOfWorkFactory, create_mysql_pool_with_retry

pytestmark = pytest.mark.db_cleanup


def test_mysql_uow_commits_on_success(db_helper) -> None:
    """Persists records when transaction scope exits without error."""
    email = "uow-commit@example.com"

    async def _exercise() -> None:
        pool = await create_mysql_pool_with_retry()
        try:
            uow_factory = MySqlUnitOfWorkFactory(pool)
            async with uow_factory.registration() as registration_port:
                await registration_port.create_pending_user(email=email, password_hash="hash")
        finally:
            pool.close()
            await pool.wait_closed()

    asyncio.run(_exercise())

    user_row = db_helper.fetch_one("SELECT id, email, status FROM users WHERE email = %s", (email,))
    assert user_row is not None
    assert user_row["email"] == email
    assert user_row["status"] == "PENDING"


def test_mysql_uow_rolls_back_on_error(db_helper) -> None:
    """Does not persist records when transaction scope raises."""
    email = "uow-rollback@example.com"

    async def _exercise() -> None:
        pool = await create_mysql_pool_with_retry()
        try:
            uow_factory = MySqlUnitOfWorkFactory(pool)
            with pytest.raises(RuntimeError, match="boom"):
                async with uow_factory.registration() as registration_port:
                    await registration_port.create_pending_user(email=email, password_hash="hash")
                    raise RuntimeError("boom")
        finally:
            pool.close()
            await pool.wait_closed()

    asyncio.run(_exercise())

    user_row = db_helper.fetch_one("SELECT id FROM users WHERE email = %s", (email,))
    assert user_row is None
