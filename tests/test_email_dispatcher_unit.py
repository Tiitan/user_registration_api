"""Unit tests for email dispatcher using dispatch ports."""

import asyncio
from contextlib import asynccontextmanager

from api.app.observability import InMemoryMetricsRecorder
from api.app.services.email_dispatcher import EmailDispatcher


class _FakeEmailProvider:
    """Minimal provider stub for dispatcher construction."""

    def __init__(self, *, error: Exception | None = None, errors: list[Exception | None] | None = None) -> None:
        """Configure provider send behavior."""
        self._error = error
        self._errors = list(errors) if errors is not None else None
        self.send_calls: list[tuple[str, str, int, int]] = []

    async def send_activation_email(self, *, recipient_email: str, code: str, user_id: int, activation_code_id: int) -> None:
        """No-op send implementation."""
        self.send_calls.append((recipient_email, code, user_id, activation_code_id))
        if self._errors is not None and self._errors:
            planned_error = self._errors.pop(0)
            if planned_error is not None:
                raise planned_error
            return None
        if self._error is not None:
            raise self._error
        return None

    async def probe(self) -> None:
        """No-op readiness probe."""
        return None


class _FakeDispatchPort:
    """In-memory dispatch port fake with configurable failures."""

    def __init__(self, *, mark_sent_failures: int = 0, undelivered_count: int = 0, fail_count_query: bool = False) -> None:
        """Configure operation outcomes."""
        self._remaining_failures = mark_sent_failures
        self._undelivered_count = undelivered_count
        self._fail_count_query = fail_count_query
        self.mark_sent_calls: list[int] = []
        self.count_calls = 0

    async def mark_activation_code_sent(self, *, activation_code_id: int) -> None:
        """Record mark-sent and fail while configured."""
        self.mark_sent_calls.append(activation_code_id)
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise RuntimeError("mark_sent_failed")

    async def count_undelivered_activation_codes(self) -> int:
        """Return configured undelivered count or raise."""
        self.count_calls += 1
        if self._fail_count_query:
            raise RuntimeError("count_failed")
        return self._undelivered_count


class _FakeUnitOfWorkFactory:
    """Return a prebuilt dispatch port inside an async context."""

    def __init__(self, dispatch_port: _FakeDispatchPort) -> None:
        """Store fake dispatch port."""
        self._dispatch_port = dispatch_port

    @asynccontextmanager
    async def dispatch(self):
        """Yield fake dispatch port."""
        yield self._dispatch_port


def test_mark_sent_retries_succeeds() -> None:
    """Returns success when sent marker eventually writes."""
    port = _FakeDispatchPort(mark_sent_failures=0)
    dispatcher = EmailDispatcher(
        uow_factory=_FakeUnitOfWorkFactory(port),  # type: ignore[arg-type]
        email_provider=_FakeEmailProvider(),
        metrics=InMemoryMetricsRecorder(),
        provider_name="fake",
    )
    dispatcher._max_retries = 2

    result = asyncio.run(dispatcher._mark_activation_code_sent_with_retries(activation_code_id=12, user_id=34))

    assert result is True
    assert port.mark_sent_calls == [12]


def test_run_dispatch_success_records_metrics_and_refreshes_gauge() -> None:
    """Records successful dispatch metrics and updates undelivered gauge."""
    metrics = InMemoryMetricsRecorder()
    provider = _FakeEmailProvider()
    port = _FakeDispatchPort(undelivered_count=0)
    dispatcher = EmailDispatcher(
        uow_factory=_FakeUnitOfWorkFactory(port),  # type: ignore[arg-type]
        email_provider=provider,
        metrics=metrics,
        provider_name="fake",
    )

    asyncio.run(
        dispatcher._run_dispatch(
            user_id=1,
            activation_code_id=11,
            recipient_email="user@example.com",
            code="1234",
        )
    )

    tags = {"provider": "fake"}
    assert provider.send_calls == [("user@example.com", "1234", 1, 11)]
    assert port.mark_sent_calls == [11]
    assert port.count_calls == 1
    assert metrics.get_counter("dispatch_attempts_total", tags=tags) == 1.0
    assert metrics.get_counter("dispatch_successes_total", tags=tags) == 1.0
    assert metrics.get_counter("dispatch_terminal_failures_total", tags=tags) == 0.0
    assert metrics.get_counter("provider_errors_total", tags={"provider": "fake", "error_type": "RuntimeError"}) == 0.0
    assert metrics.get_counter("provider_retry_attempt_failures_total", tags={"provider": "fake", "error_type": "TimeoutError"}) == 0.0
    latency = metrics.get_histogram("provider_latency_ms", tags=tags)
    assert latency.count == 1
    assert latency.total >= 0.0
    assert metrics.get_gauge("activation_codes_undelivered") == 0.0


def test_run_dispatch_provider_retryable_failures_then_success_records_retry_metrics() -> None:
    """Retries transient provider failures and succeeds without terminal provider error."""
    metrics = InMemoryMetricsRecorder()
    provider = _FakeEmailProvider(errors=[TimeoutError("timeout"), ConnectionError("connection"), None])
    port = _FakeDispatchPort(undelivered_count=0)
    dispatcher = EmailDispatcher(
        uow_factory=_FakeUnitOfWorkFactory(port),  # type: ignore[arg-type]
        email_provider=provider,
        metrics=metrics,
        provider_name="fake",
    )
    dispatcher._max_retries = 3
    dispatcher._retry_base_delay_seconds = 0.0
    dispatcher._retry_max_delay_seconds = 0.0

    asyncio.run(
        dispatcher._run_dispatch(
            user_id=14,
            activation_code_id=114,
            recipient_email="retry-success@example.com",
            code="2233",
        )
    )

    tags = {"provider": "fake"}
    assert len(provider.send_calls) == 3
    assert port.mark_sent_calls == [114]
    assert metrics.get_counter("dispatch_attempts_total", tags=tags) == 1.0
    assert metrics.get_counter("dispatch_successes_total", tags=tags) == 1.0
    assert metrics.get_counter("dispatch_terminal_failures_total", tags=tags) == 0.0
    assert metrics.get_counter("provider_retry_attempt_failures_total", tags={"provider": "fake", "error_type": "TimeoutError"}) == 1.0
    assert metrics.get_counter("provider_retry_attempt_failures_total", tags={"provider": "fake", "error_type": "ConnectionError"}) == 1.0
    assert metrics.get_counter("provider_errors_total", tags={"provider": "fake", "error_type": "TimeoutError"}) == 0.0
    assert metrics.get_counter("provider_errors_total", tags={"provider": "fake", "error_type": "ConnectionError"}) == 0.0
    latency = metrics.get_histogram("provider_latency_ms", tags=tags)
    assert latency.count == 1
    assert latency.total >= 0.0


def test_run_dispatch_provider_retryable_failure_exhausts_attempts() -> None:
    """Marks terminal provider failure after transient retries are exhausted."""
    metrics = InMemoryMetricsRecorder()
    provider = _FakeEmailProvider(errors=[TimeoutError("timeout-1"), TimeoutError("timeout-2"), TimeoutError("timeout-3")])
    port = _FakeDispatchPort(undelivered_count=4)
    dispatcher = EmailDispatcher(
        uow_factory=_FakeUnitOfWorkFactory(port),  # type: ignore[arg-type]
        email_provider=provider,
        metrics=metrics,
        provider_name="fake",
    )
    dispatcher._max_retries = 3
    dispatcher._retry_base_delay_seconds = 0.0
    dispatcher._retry_max_delay_seconds = 0.0

    asyncio.run(
        dispatcher._run_dispatch(
            user_id=15,
            activation_code_id=115,
            recipient_email="retry-fail@example.com",
            code="3344",
        )
    )

    tags = {"provider": "fake"}
    assert len(provider.send_calls) == 3
    assert port.mark_sent_calls == []
    assert metrics.get_counter("dispatch_attempts_total", tags=tags) == 1.0
    assert metrics.get_counter("dispatch_successes_total", tags=tags) == 0.0
    assert metrics.get_counter("dispatch_terminal_failures_total", tags=tags) == 1.0
    assert metrics.get_counter("provider_retry_attempt_failures_total", tags={"provider": "fake", "error_type": "TimeoutError"}) == 2.0
    assert metrics.get_counter("provider_errors_total", tags={"provider": "fake", "error_type": "TimeoutError"}) == 1.0
    latency = metrics.get_histogram("provider_latency_ms", tags=tags)
    assert latency.count == 1
    assert latency.total >= 0.0
    assert metrics.get_gauge("activation_codes_undelivered") == 4.0


def test_run_dispatch_provider_failure_records_terminal_metrics_and_refreshes_gauge() -> None:
    """Records provider failures as terminal and refreshes undelivered gauge."""
    metrics = InMemoryMetricsRecorder()
    provider = _FakeEmailProvider(error=RuntimeError("provider-down"))
    port = _FakeDispatchPort(undelivered_count=5)
    dispatcher = EmailDispatcher(
        uow_factory=_FakeUnitOfWorkFactory(port),  # type: ignore[arg-type]
        email_provider=provider,
        metrics=metrics,
        provider_name="fake",
    )

    asyncio.run(
        dispatcher._run_dispatch(
            user_id=2,
            activation_code_id=22,
            recipient_email="error@example.com",
            code="9876",
        )
    )

    tags = {"provider": "fake"}
    assert provider.send_calls == [("error@example.com", "9876", 2, 22)]
    assert port.mark_sent_calls == []
    assert port.count_calls == 1
    assert metrics.get_counter("dispatch_attempts_total", tags=tags) == 1.0
    assert metrics.get_counter("dispatch_successes_total", tags=tags) == 0.0
    assert metrics.get_counter("dispatch_terminal_failures_total", tags=tags) == 1.0
    assert metrics.get_counter("provider_retry_attempt_failures_total", tags={"provider": "fake", "error_type": "RuntimeError"}) == 0.0
    assert metrics.get_counter("provider_errors_total", tags={"provider": "fake", "error_type": "RuntimeError"}) == 1.0
    latency = metrics.get_histogram("provider_latency_ms", tags=tags)
    assert latency.count == 1
    assert latency.total >= 0.0
    assert metrics.get_gauge("activation_codes_undelivered") == 5.0


def test_run_dispatch_persistence_failure_records_terminal_metrics_and_refreshes_gauge() -> None:
    """Treats sent_at persistence failure as terminal and refreshes gauge."""
    metrics = InMemoryMetricsRecorder()
    provider = _FakeEmailProvider()
    port = _FakeDispatchPort(mark_sent_failures=1, undelivered_count=3)
    dispatcher = EmailDispatcher(
        uow_factory=_FakeUnitOfWorkFactory(port),  # type: ignore[arg-type]
        email_provider=provider,
        metrics=metrics,
        provider_name="fake",
    )
    dispatcher._max_retries = 1
    dispatcher._retry_base_delay_seconds = 0.0
    dispatcher._retry_max_delay_seconds = 0.0

    asyncio.run(
        dispatcher._run_dispatch(
            user_id=3,
            activation_code_id=33,
            recipient_email="persist@example.com",
            code="5555",
        )
    )

    tags = {"provider": "fake"}
    assert provider.send_calls == [("persist@example.com", "5555", 3, 33)]
    assert port.mark_sent_calls == [33]
    assert port.count_calls == 1
    assert metrics.get_counter("dispatch_attempts_total", tags=tags) == 1.0
    assert metrics.get_counter("dispatch_successes_total", tags=tags) == 0.0
    assert metrics.get_counter("dispatch_terminal_failures_total", tags=tags) == 1.0
    assert metrics.get_counter("provider_retry_attempt_failures_total", tags={"provider": "fake", "error_type": "RuntimeError"}) == 0.0
    assert metrics.get_counter("provider_errors_total", tags={"provider": "fake", "error_type": "RuntimeError"}) == 0.0
    latency = metrics.get_histogram("provider_latency_ms", tags=tags)
    assert latency.count == 1
    assert latency.total >= 0.0
    assert metrics.get_gauge("activation_codes_undelivered") == 3.0


def test_mark_sent_retries_returns_false_after_terminal_failure() -> None:
    """Returns false when all retries fail."""
    port = _FakeDispatchPort(mark_sent_failures=3)
    dispatcher = EmailDispatcher(
        uow_factory=_FakeUnitOfWorkFactory(port),  # type: ignore[arg-type]
        email_provider=_FakeEmailProvider(),
        metrics=InMemoryMetricsRecorder(),
        provider_name="fake",
    )
    dispatcher._max_retries = 3
    dispatcher._retry_base_delay_seconds = 0.0
    dispatcher._retry_max_delay_seconds = 0.0

    result = asyncio.run(dispatcher._mark_activation_code_sent_with_retries(activation_code_id=13, user_id=35))

    assert result is False
    assert port.mark_sent_calls == [13, 13, 13]


def test_refresh_undelivered_metric_updates_gauge() -> None:
    """Writes undelivered gauge from dispatch port count."""
    metrics = InMemoryMetricsRecorder()
    port = _FakeDispatchPort(undelivered_count=7)
    dispatcher = EmailDispatcher(
        uow_factory=_FakeUnitOfWorkFactory(port),  # type: ignore[arg-type]
        email_provider=_FakeEmailProvider(),
        metrics=metrics,
        provider_name="fake",
    )

    asyncio.run(dispatcher._refresh_undelivered_activation_codes_metric())

    assert port.count_calls == 1
    assert metrics.get_gauge("activation_codes_undelivered") == 7.0


def test_refresh_undelivered_metric_ignores_query_failure() -> None:
    """Leaves gauge unchanged when count query fails."""
    metrics = InMemoryMetricsRecorder()
    metrics.set("activation_codes_undelivered", 2.0)
    port = _FakeDispatchPort(fail_count_query=True)
    dispatcher = EmailDispatcher(
        uow_factory=_FakeUnitOfWorkFactory(port),  # type: ignore[arg-type]
        email_provider=_FakeEmailProvider(),
        metrics=metrics,
        provider_name="fake",
    )

    asyncio.run(dispatcher._refresh_undelivered_activation_codes_metric())

    assert port.count_calls == 1
    assert metrics.get_gauge("activation_codes_undelivered") == 2.0
