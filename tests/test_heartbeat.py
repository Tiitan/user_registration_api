"""Tests for heartbeat endpoint and lifespan startup behavior."""

from fastapi.testclient import TestClient

from api.app import main


class _FakePool:
    """Minimal fake pool used to bypass real DB setup."""

    def close(self) -> None:
        """Match pool close interface."""
        return None

    async def wait_closed(self) -> None:
        """Match pool wait_closed interface."""
        return None


def test_heartbeat_returns_ok(monkeypatch) -> None:
    """Returns liveness payload when app starts successfully."""
    async def _fake_create_mysql_pool_with_retry() -> _FakePool:
        return _FakePool()

    monkeypatch.setattr(
        "api.app.lifespan.create_mysql_pool_with_retry",
        _fake_create_mysql_pool_with_retry,
    )

    with TestClient(main.app) as client:
        response = client.get("/heartbeat")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
