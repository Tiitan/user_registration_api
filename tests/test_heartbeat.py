"""Tests for heartbeat endpoint and lifespan startup behavior."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app.routers.heartbeat import router as heartbeat_router
from api.app.routers.observability import router as observability_router


def test_heartbeat_returns_ok() -> None:
    """Returns liveness payload without requiring DB-backed app lifespan."""
    app = FastAPI()
    app.include_router(heartbeat_router)
    with TestClient(app) as client:
        response = client.get("/heartbeat")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
