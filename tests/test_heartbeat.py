from fastapi.testclient import TestClient

from api.app import main


class _FakePool:
    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


def test_heartbeat_returns_ok(monkeypatch) -> None:
    async def _fake_create_mysql_pool_with_retry() -> _FakePool:
        return _FakePool()

    monkeypatch.setattr(
        "api.app.db.lifespan.create_mysql_pool_with_retry",
        _fake_create_mysql_pool_with_retry,
    )

    with TestClient(main.app) as client:
        response = client.get("/heartbeat")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
