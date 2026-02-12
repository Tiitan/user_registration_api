"""Tests for heartbeat endpoint and lifespan startup behavior."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app.routers import heartbeat_router, observability_router


def test_heartbeat_returns_ok() -> None:
    """Returns liveness payload without requiring DB-backed app lifespan."""
    app = FastAPI()
    app.include_router(heartbeat_router)
    with TestClient(app) as client:
        response = client.get("/heartbeat")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class _FakeCursor:
    def __init__(self, *, should_fail: bool) -> None:
        self._should_fail = should_fail

    async def execute(self, _query: str) -> None:
        if self._should_fail:
            raise RuntimeError("db unavailable")


class _FakeConnection:
    def __init__(self, *, should_fail: bool) -> None:
        self._should_fail = should_fail

    @asynccontextmanager
    async def cursor(self) -> AsyncIterator[_FakeCursor]:
        yield _FakeCursor(should_fail=self._should_fail)


class _FakePool:
    def __init__(self, *, should_fail: bool) -> None:
        self._should_fail = should_fail

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[_FakeConnection]:
        yield _FakeConnection(should_fail=self._should_fail)


class _FakeEmailProvider:
    def __init__(self, *, should_fail_probe: bool) -> None:
        self._should_fail_probe = should_fail_probe

    async def probe(self) -> None:
        if self._should_fail_probe:
            raise RuntimeError("provider unavailable")


def test_readiness_returns_ok_when_database_probe_succeeds() -> None:
    app = FastAPI()
    app.include_router(heartbeat_router)
    app.state.db_pool = _FakePool(should_fail=False)
    app.state.email_provider = _FakeEmailProvider(should_fail_probe=False)
    with TestClient(app) as client:
        response = client.get("/readiness")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_503_when_database_probe_fails() -> None:
    app = FastAPI()
    app.include_router(heartbeat_router)
    app.state.db_pool = _FakePool(should_fail=True)
    app.state.email_provider = _FakeEmailProvider(should_fail_probe=False)
    with TestClient(app) as client:
        response = client.get("/readiness")

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}


def test_readiness_returns_503_when_email_provider_probe_fails() -> None:
    app = FastAPI()
    app.include_router(heartbeat_router)
    app.state.db_pool = _FakePool(should_fail=False)
    app.state.email_provider = _FakeEmailProvider(should_fail_probe=True)
    with TestClient(app) as client:
        response = client.get("/readiness")

    assert response.status_code == 503
    assert response.json() == {"detail": "email provider unavailable"}


def test_metrics_endpoint_returns_prometheus_content_type() -> None:
    """Exposes a Prometheus-compatible metrics endpoint."""
    app = FastAPI()
    app.include_router(observability_router)
    app.state.metrics = None
    with TestClient(app) as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "version=" in response.headers["content-type"]
