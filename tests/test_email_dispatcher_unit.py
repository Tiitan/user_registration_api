"""Unit tests for email dispatcher using dispatch ports."""

import asyncio
from contextlib import asynccontextmanager

from api.app.observability import InMemoryMetricsRecorder
from api.app.services.email_dispatcher import EmailDispatcher


class _FakeEmailProvider:
    """Minimal provider stub for dispatcher construction."""

    async def send_activation_email(self, *, recipient_email: str, code: str, user_id: int, activation_code_id: int) -> None:
        """No-op send implementation."""
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
