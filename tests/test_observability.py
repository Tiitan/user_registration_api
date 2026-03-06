"""Integration tests for logging, request IDs, and metrics."""

import logging

import pytest

from api.app.observability import CORRELATION_ID_HEADER, InMemoryMetricsRecorder, REQUEST_ID_HEADER

pytestmark = pytest.mark.db_cleanup


class _ApiLogPropagation:
    """Context manager that enables API logger propagation for caplog."""

    def __init__(self) -> None:
        """Capture and store logger propagation state."""
        self._logger = logging.getLogger("api")
        self._original = self._logger.propagate

    def __enter__(self) -> None:
        """Enable propagation while inside context."""
        self._logger.propagate = True
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        """Restore original propagation state."""
        self._logger.propagate = self._original


def test_request_ids_echoed_when_provided(client) -> None:
    """Echoes request and correlation IDs from incoming headers."""
    headers = {
        REQUEST_ID_HEADER: "req-123",
        CORRELATION_ID_HEADER: "corr-123",
    }
    response = client.get("/heartbeat", headers=headers)

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "req-123"
    assert response.headers[CORRELATION_ID_HEADER] == "corr-123"


def test_request_ids_generated_when_missing_and_present_in_logs(client, caplog) -> None:
    """Generates IDs when absent and attaches them to logs."""
    with _ApiLogPropagation():
        caplog.set_level(logging.INFO)
        response = client.post("/v1/users", json={"email": "obs@example.com", "password": "StrongPass123"})
        client.app.state.email_dispatcher.wait_until_idle(timeout=2.0)

        assert response.status_code == 201
        generated_request_id = response.headers[REQUEST_ID_HEADER]
        generated_correlation_id = response.headers[CORRELATION_ID_HEADER]
        assert generated_request_id
        assert generated_correlation_id

        matching_logs = [
            record
            for record in caplog.records
            if getattr(record, "request_id", None) == generated_request_id
            and getattr(record, "correlation_id", None) == generated_correlation_id
        ]
        assert matching_logs


def test_domain_exception_log_contains_context_and_error_code(client, caplog) -> None:
    """Includes context IDs and error code in domain error logs."""
    with _ApiLogPropagation():
        caplog.set_level(logging.WARNING)
        headers = {
            REQUEST_ID_HEADER: "req-exc",
            CORRELATION_ID_HEADER: "corr-exc",
        }

        response = client.post("/v1/users/activate", json={"code": "1234"}, headers=headers)

        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "invalid_credentials"

        error_logs = [
            record
            for record in caplog.records
            if getattr(record, "event", None) == "api_error"
            and getattr(record, "error_code", None) == "invalid_credentials"
        ]
        assert error_logs
        assert any(
            getattr(record, "request_id", None) == "req-exc"
            and getattr(record, "correlation_id", None) == "corr-exc"
            for record in error_logs
        )


def test_dispatch_metrics_success_and_undelivered_gauge(client) -> None:
    """Tracks successful dispatch counters, latency, and gauge."""
    metrics = client.app.state.metrics
    assert isinstance(metrics, InMemoryMetricsRecorder)
    metrics.reset()

    response = client.post("/v1/users", json={"email": "metrics-success@example.com", "password": "StrongPass123"})
    assert response.status_code == 201
    client.app.state.email_dispatcher.wait_until_idle(timeout=2.0)

    tags = {"provider": "mock_email_provider"}
    assert metrics.get_counter("dispatch_attempts_total", tags=tags) == 1.0
    assert metrics.get_counter("dispatch_successes_total", tags=tags) == 1.0
    assert metrics.get_counter("dispatch_terminal_failures_total", tags=tags) == 0.0
    latency = metrics.get_histogram("provider_latency_ms", tags=tags)
    assert latency.count == 1
    assert latency.total >= 0.0
    assert metrics.get_gauge("activation_codes_undelivered") == 0.0


def test_dispatch_metrics_terminal_failure_tracks_provider_errors(client) -> None:
    """Tracks terminal failures and provider error metrics."""
    metrics = client.app.state.metrics
    assert isinstance(metrics, InMemoryMetricsRecorder)
    metrics.reset()

    async def _raise_provider_error(**_: object) -> None:
        raise RuntimeError("provider-down")

    client.app.state.email_provider.send_activation_email = _raise_provider_error

    response = client.post("/v1/users", json={"email": "metrics-failure@example.com", "password": "StrongPass123"})
    assert response.status_code == 201
    client.app.state.email_dispatcher.wait_until_idle(timeout=2.0)

    tags = {"provider": "mock_email_provider"}
    assert metrics.get_counter("dispatch_attempts_total", tags=tags) == 1.0
    assert metrics.get_counter("dispatch_successes_total", tags=tags) == 0.0
    assert metrics.get_counter("dispatch_terminal_failures_total", tags=tags) == 1.0
    assert metrics.get_counter("provider_errors_total", tags={"provider": "mock_email_provider", "error_type": "RuntimeError"}) == 1.0
    assert metrics.get_gauge("activation_codes_undelivered") == 1.0


def test_dispatch_metrics_provider_retry_attempt_failures_tracked(client) -> None:
    """Tracks transient provider retry failures while preserving dispatch-level metric semantics."""
    metrics = client.app.state.metrics
    assert isinstance(metrics, InMemoryMetricsRecorder)
    metrics.reset()
    attempt_counter = {"value": 0}

    async def _flaky_provider(**_: object) -> None:
        attempt_counter["value"] += 1
        if attempt_counter["value"] < 3:
            raise TimeoutError("provider-timeout")

    client.app.state.email_provider.send_activation_email = _flaky_provider

    response = client.post("/v1/users", json={"email": "metrics-retry@example.com", "password": "StrongPass123"})
    assert response.status_code == 201
    client.app.state.email_dispatcher.wait_until_idle(timeout=2.0)

    tags = {"provider": "mock_email_provider"}
    assert metrics.get_counter("dispatch_attempts_total", tags=tags) == 1.0
    assert metrics.get_counter("dispatch_successes_total", tags=tags) == 1.0
    assert metrics.get_counter("dispatch_terminal_failures_total", tags=tags) == 0.0
    assert metrics.get_counter("provider_retry_attempt_failures_total", tags={"provider": "mock_email_provider", "error_type": "TimeoutError"}) == 2.0
    assert metrics.get_counter("provider_errors_total", tags={"provider": "mock_email_provider", "error_type": "TimeoutError"}) == 0.0
    latency = metrics.get_histogram("provider_latency_ms", tags=tags)
    assert latency.count == 1
    assert latency.total >= 0.0


def test_metrics_endpoint_exports_dispatch_metrics(client) -> None:
    """Exports dispatcher metrics in Prometheus exposition format."""
    metrics = client.app.state.metrics
    assert isinstance(metrics, InMemoryMetricsRecorder)
    metrics.reset()

    response = client.post("/v1/users", json={"email": "scrape@example.com", "password": "StrongPass123"})
    assert response.status_code == 201
    client.app.state.email_dispatcher.wait_until_idle(timeout=2.0)

    scrape = client.get("/metrics")
    assert scrape.status_code == 200
    assert 'dispatch_attempts_total{provider="mock_email_provider"} 1.0' in scrape.text
    assert 'dispatch_successes_total{provider="mock_email_provider"} 1.0' in scrape.text
    assert 'provider_latency_ms_count{provider="mock_email_provider"} 1' in scrape.text
