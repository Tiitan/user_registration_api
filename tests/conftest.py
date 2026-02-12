"""Shared pytest fixtures and DB helpers for integration tests."""

import asyncio
import importlib
import os
import socket
import types
from collections.abc import Generator

import asyncmy
import pytest
from asyncmy.cursors import DictCursor
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app.config import get_settings


def _configure_mysql_host_for_test_environment() -> None:
    """Use localhost when Docker hostname is not resolvable."""
    configured_host = os.environ.get("MYSQL_HOST", "mysql")
    if configured_host != "mysql":
        return
    try:
        socket.getaddrinfo("mysql", 3306)
    except OSError:
        os.environ["MYSQL_HOST"] = "127.0.0.1"


_configure_mysql_host_for_test_environment()
get_settings.cache_clear()

USERS_INTEGRATION_FILES = {"test_create_user.py", "test_activate_user.py", "test_observability.py"}
main = importlib.import_module("api.app.main")


class DbHelper:
    """Convenience wrapper for async MySQL operations in tests."""

    def __init__(self) -> None:
        """Initialize database connection parameters from settings."""
        settings = get_settings()
        self._connect_kwargs = {
            "host": settings.mysql_host,
            "port": settings.mysql_port,
            "user": settings.mysql_user,
            "password": settings.mysql_password,
            "db": settings.mysql_database,
            "autocommit": True,
        }

    def execute(self, query: str, args: tuple | None = None) -> None:
        """Run a statement without returning rows."""
        asyncio.run(self._execute(query=query, args=args))

    def fetch_one(self, query: str, args: tuple | None = None) -> dict | None:
        """Return one row as a dictionary or `None`."""
        return asyncio.run(self._fetch_one(query=query, args=args))

    def fetch_all(self, query: str, args: tuple | None = None) -> list[dict]:
        """Return all rows as dictionaries."""
        return asyncio.run(self._fetch_all(query=query, args=args))

    def count(self, query: str, args: tuple | None = None) -> int:
        """Return the first numeric value from a count-like query."""
        row = self.fetch_one(query=query, args=args)
        if row is None:
            return 0
        return int(next(iter(row.values())))

    def latest_unused_activation_code(self, email: str) -> dict:
        """Return the latest unused activation code row for an email."""
        row = self.fetch_one(
            "SELECT ac.id, ac.code, ac.sent_at, ac.used_at, ac.attempt_count, ac.created_at "
            "FROM activation_codes ac "
            "JOIN users u ON u.id = ac.user_id "
            "WHERE u.email = %s AND ac.used_at IS NULL "
            "ORDER BY ac.created_at DESC, ac.id DESC "
            "LIMIT 1",
            (email,),
        )
        if row is None:
            raise AssertionError(f"No unused activation code found for {email}")
        return row

    async def _execute(self, query: str, args: tuple | None) -> None:
        """Async implementation backing `execute`."""
        connection = await asyncmy.connect(**self._connect_kwargs)
        try:
            async with connection.cursor(DictCursor) as cursor:
                await cursor.execute(query, args)
        finally:
            connection.close()

    async def _fetch_one(self, query: str, args: tuple | None) -> dict | None:
        """Async implementation backing `fetch_one`."""
        connection = await asyncmy.connect(**self._connect_kwargs)
        try:
            async with connection.cursor(DictCursor) as cursor:
                await cursor.execute(query, args)
                return await cursor.fetchone()
        finally:
            connection.close()

    async def _fetch_all(self, query: str, args: tuple | None) -> list[dict]:
        """Async implementation backing `fetch_all`."""
        connection = await asyncmy.connect(**self._connect_kwargs)
        try:
            async with connection.cursor(DictCursor) as cursor:
                await cursor.execute(query, args)
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        finally:
            connection.close()


@pytest.fixture(scope="session")
def db_helper() -> DbHelper:
    """Provide a reusable DB helper for integration tests."""
    return DbHelper()


@pytest.fixture(autouse=True)
def clean_tables_for_users_integration_tests(request: pytest.FixtureRequest, db_helper: DbHelper) -> None:
    """Clean user tables before each users integration test."""
    if request.node.fspath.basename not in USERS_INTEGRATION_FILES:
        return
    db_helper.execute("DELETE FROM activation_codes")
    db_helper.execute("DELETE FROM users")


@pytest.fixture
def client(request: pytest.FixtureRequest) -> Generator[TestClient, None, None]:
    """Provide a TestClient with a helper to wait for background tasks."""
    if request.node.fspath.basename not in USERS_INTEGRATION_FILES:
        pytest.skip("Integration TestClient fixture is only for users integration tests.")
    with TestClient(main.app) as test_client:
        app = test_client.app
        assert isinstance(app, FastAPI)
        dispatcher = app.state.email_dispatcher

        def _wait_until_idle(self, timeout: float = 2.0) -> None:
            tasks = list(self._background_tasks)
            if not tasks:
                return
            loop = tasks[0].get_loop()
            async def _await_tasks() -> list[object]:
                return list(await asyncio.gather(*tasks, return_exceptions=True))

            wait_future = asyncio.run_coroutine_threadsafe(_await_tasks(), loop)
            results = wait_future.result(timeout=timeout)
            errors = [str(result) for result in results if isinstance(result, Exception)]
            if errors:
                raise AssertionError(f"Background email dispatch task failure(s): {errors}")

        dispatcher.wait_until_idle = types.MethodType(_wait_until_idle, dispatcher)
        yield test_client
