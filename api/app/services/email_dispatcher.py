"""Background email dispatch and delivery metrics service."""

import asyncio
import logging
import secrets
from dataclasses import dataclass
from enum import Enum
from time import perf_counter

from api.app.config import get_settings
from api.app.integrations import EmailProvider
from api.app.observability import MetricsRecorder, NoOpMetricsRecorder
from api.app.unit_of_work import UnitOfWorkFactory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _DispatchContext:
    """Immutable context for a single dispatch run."""

    user_id: int
    activation_code_id: int
    recipient_email: str
    code: str
    provider: str
    tags: dict[str, str]


class _DispatchOutcomeKind(str, Enum):
    """Outcome kinds produced by the dispatch workflow."""

    SUCCESS = "success"
    PROVIDER_FAILURE = "provider_failure"
    PERSISTENCE_FAILURE = "persistence_failure"


@dataclass(frozen=True)
class _DispatchOutcome:
    """Result details for dispatch stages and completion."""

    kind: _DispatchOutcomeKind
    duration_ms: float
    error_type: str | None = None
    error: Exception | None = None


class EmailDispatcher:
    """Dispatch activation emails with retries and metrics."""

    def __init__(self, uow_factory: UnitOfWorkFactory, email_provider: EmailProvider, *, metrics: MetricsRecorder | None = None, provider_name: str | None = None) -> None:
        """Initialize dispatcher dependencies and retry settings."""
        settings = get_settings()
        self._uow_factory = uow_factory
        self._email_provider = email_provider
        self._provider_name = provider_name or email_provider.__class__.__name__.lower()
        self._metrics: MetricsRecorder = metrics or NoOpMetricsRecorder()
        self._max_retries = settings.email_provider_max_retries
        self._retry_base_delay_seconds = settings.email_provider_retry_base_delay_seconds
        self._retry_max_delay_seconds = settings.email_provider_retry_max_delay_seconds
        self._dispatch_semaphore = asyncio.Semaphore(settings.email_dispatch_max_concurrency)
        self._background_tasks: set[asyncio.Task[None]] = set()

    def dispatch_activation_email(self, *, user_id: int, activation_code_id: int, recipient_email: str, code: str) -> None:
        """Schedule an activation email in a background task."""
        task = asyncio.create_task(self._run_dispatch(user_id=user_id, activation_code_id=activation_code_id, recipient_email=recipient_email, code=code))
        self._background_tasks.add(task)

        def _on_done(done_task: asyncio.Task[None]) -> None:
            self._background_tasks.discard(done_task)
            if done_task.cancelled():
                logger.warning("Background email dispatch task was cancelled")
                return
            error = done_task.exception()
            if error is not None:
                logger.exception("Background email dispatch failed unexpectedly: %s", str(error))

        task.add_done_callback(_on_done)

    async def _run_dispatch(self, *, user_id: int, activation_code_id: int, recipient_email: str, code: str) -> None:
        """Run one dispatch attempt and record outcomes."""
        async with self._dispatch_semaphore:
            context = self._build_context(user_id=user_id, activation_code_id=activation_code_id, recipient_email=recipient_email, code=code)
            self._emit_dispatch_started(context)
            try:
                provider_outcome = await self._send_provider_email_with_retries(context)
                if provider_outcome.kind is _DispatchOutcomeKind.PROVIDER_FAILURE:
                    self._emit_provider_failure(context, provider_outcome)
                    return

                sent_at_marked = await self._mark_activation_code_sent_with_retries(activation_code_id=context.activation_code_id, user_id=context.user_id)
                if sent_at_marked:
                    completion_outcome = _DispatchOutcome(kind=_DispatchOutcomeKind.SUCCESS, duration_ms=provider_outcome.duration_ms)
                else:
                    completion_outcome = _DispatchOutcome(kind=_DispatchOutcomeKind.PERSISTENCE_FAILURE, duration_ms=provider_outcome.duration_ms)
                self._emit_dispatch_completed(context, completion_outcome)
            finally:
                await self._refresh_undelivered_activation_codes_metric()

    async def _mark_activation_code_sent_with_retries(self, *, activation_code_id: int, user_id: int) -> bool:
        """Retry sent-at persistence with exponential backoff and jitter."""
        for attempt in range(1, self._max_retries + 1):
            try:
                await self._mark_activation_code_sent(activation_code_id=activation_code_id)
                return True
            except Exception as exc:
                final_attempt = attempt >= self._max_retries
                self._log_sent_at_retry_failure(activation_code_id=activation_code_id, user_id=user_id, attempt=attempt, error=exc)
                if final_attempt:
                    return False
                await asyncio.sleep(self._compute_retry_delay_seconds(attempt=attempt))
        return False

    def _build_context(self, *, user_id: int, activation_code_id: int, recipient_email: str, code: str) -> _DispatchContext:
        """Build immutable dispatch context for this run."""
        provider = self._provider_name
        return _DispatchContext(user_id=user_id, activation_code_id=activation_code_id, recipient_email=recipient_email, code=code, provider=provider, tags={"provider": provider})

    async def _send_provider_email_with_retries(self, context: _DispatchContext) -> _DispatchOutcome:
        """Send activation email with retry loop for transient provider errors."""
        for attempt in range(1, self._max_retries + 1):
            started = perf_counter()
            try:
                await self._email_provider.send_activation_email(recipient_email=context.recipient_email, code=context.code, user_id=context.user_id, activation_code_id=context.activation_code_id)
                return _DispatchOutcome(kind=_DispatchOutcomeKind.SUCCESS, duration_ms=(perf_counter() - started) * 1000)
            except Exception as error:
                duration_ms = (perf_counter() - started) * 1000
                final_attempt = attempt >= self._max_retries
                if final_attempt or not self._is_retryable_provider_error(error):
                    return _DispatchOutcome(kind=_DispatchOutcomeKind.PROVIDER_FAILURE, duration_ms=duration_ms, error_type=error.__class__.__name__, error=error)
                self._metrics.inc("provider_retry_attempt_failures_total", tags={"provider": context.provider, "error_type": error.__class__.__name__})
                self._log_provider_retry_failure(context=context, attempt=attempt, error=error)
                await asyncio.sleep(self._compute_retry_delay_seconds(attempt=attempt))
        return _DispatchOutcome(kind=_DispatchOutcomeKind.PROVIDER_FAILURE, duration_ms=0.0, error_type="RetriesExhausted", error=None)

    def _is_retryable_provider_error(self, error: Exception) -> bool:
        """Return whether provider error should be retried."""
        return isinstance(error, (TimeoutError, ConnectionError, OSError))

    def _emit_dispatch_started(self, context: _DispatchContext) -> None:
        """Record and log dispatch start."""
        self._metrics.inc("dispatch_attempts_total", tags=context.tags)
        extra = self._dispatch_log_extra(context=context, event="dispatch_attempt")
        logger.info("Activation email dispatch started user_id=%s activation_code_id=%s", context.user_id, context.activation_code_id, extra=extra)

    def _emit_provider_latency(self, context: _DispatchContext, *, duration_ms: float) -> None:
        """Observe provider call latency."""
        self._metrics.observe("provider_latency_ms", duration_ms, tags=context.tags)

    def _emit_provider_failure(self, context: _DispatchContext, outcome: _DispatchOutcome) -> None:
        """Record metrics and logs for terminal provider failures."""
        self._emit_provider_latency(context, duration_ms=outcome.duration_ms)
        error_type = outcome.error_type or "UnknownError"
        self._metrics.inc("provider_errors_total", tags={"provider": context.provider, "error_type": error_type})
        self._metrics.inc("dispatch_terminal_failures_total", tags=context.tags)
        extra = self._dispatch_log_extra(context=context, event="dispatch_failure_terminal", error_type=error_type, duration_ms=outcome.duration_ms)
        if outcome.error is None:
            logger.error("Activation email provider call failed user_id=%s activation_code_id=%s", context.user_id, context.activation_code_id, extra=extra)
            return
        error_info = (type(outcome.error), outcome.error, outcome.error.__traceback__)
        logger.error("Activation email provider call failed user_id=%s activation_code_id=%s", context.user_id, context.activation_code_id, extra=extra, exc_info=error_info)

    def _emit_dispatch_completed(self, context: _DispatchContext, outcome: _DispatchOutcome) -> None:
        """Record completion observability for success and persistence failures."""
        self._emit_provider_latency(context, duration_ms=outcome.duration_ms)
        extra = self._dispatch_log_extra(context=context, event="dispatch_success", duration_ms=outcome.duration_ms)
        if outcome.kind is _DispatchOutcomeKind.SUCCESS:
            self._metrics.inc("dispatch_successes_total", tags=context.tags)
            logger.info("Activation email delivered user_id=%s activation_code_id=%s", context.user_id, context.activation_code_id, extra=extra)
            return
        self._metrics.inc("dispatch_terminal_failures_total", tags=context.tags)
        extra = self._dispatch_log_extra(context=context, event="dispatch_failure_terminal", duration_ms=outcome.duration_ms)
        logger.error("Activation email was sent but sent_at update failed user_id=%s activation_code_id=%s", context.user_id, context.activation_code_id, extra=extra)

    def _dispatch_log_extra(self, *, context: _DispatchContext, event: str, duration_ms: float | None = None, error_type: str | None = None) -> dict[str, object]:
        """Build common structured log payload for dispatch events."""
        extra: dict[str, object] = {"event": event, "user_id": context.user_id, "activation_code_id": context.activation_code_id, "provider": context.provider}
        if error_type is not None:
            extra["error_type"] = error_type
        if duration_ms is not None:
            extra["duration_ms"] = round(duration_ms, 3)
        return extra

    def _sent_at_retry_extra(self, *, activation_code_id: int, user_id: int, error: Exception) -> dict[str, object]:
        """Build retry failure structured log payload."""
        return {"event": "dispatch_sent_at_retry", "user_id": user_id, "activation_code_id": activation_code_id, "provider": self._provider_name, "error_type": error.__class__.__name__}

    def _log_sent_at_retry_failure(self, *, activation_code_id: int, user_id: int, attempt: int, error: Exception) -> None:
        """Log sent_at retry failure with consistent structured context."""
        extra = self._sent_at_retry_extra(activation_code_id=activation_code_id, user_id=user_id, error=error)
        logger.warning("sent_at update failed user_id=%s activation_code_id=%s attempt=%s/%s error=%s", user_id, activation_code_id, attempt, self._max_retries, str(error), extra=extra)

    def _provider_retry_extra(self, *, context: _DispatchContext, attempt: int, error: Exception) -> dict[str, object]:
        """Build provider retry structured log payload."""
        return {
            "event": "dispatch_provider_retry",
            "user_id": context.user_id,
            "activation_code_id": context.activation_code_id,
            "provider": context.provider,
            "attempt": attempt,
            "max_attempts": self._max_retries,
            "error_type": error.__class__.__name__,
        }

    def _log_provider_retry_failure(self, *, context: _DispatchContext, attempt: int, error: Exception) -> None:
        """Log retryable provider failure before sleeping."""
        extra = self._provider_retry_extra(context=context, attempt=attempt, error=error)
        logger.warning(
            "Provider send failed and will be retried user_id=%s activation_code_id=%s attempt=%s/%s error=%s",
            context.user_id,
            context.activation_code_id,
            attempt,
            self._max_retries,
            str(error),
            extra=extra,
        )

    async def _mark_activation_code_sent(self, *, activation_code_id: int) -> None:
        """Persist `sent_at` for a delivered activation code."""
        async with self._uow_factory.dispatch() as dispatch_port:
            await dispatch_port.mark_activation_code_sent(activation_code_id=activation_code_id)

    async def _refresh_undelivered_activation_codes_metric(self) -> None:
        """Update gauge with current number of undelivered codes."""
        try:
            async with self._uow_factory.dispatch() as dispatch_port:
                undelivered_count = await dispatch_port.count_undelivered_activation_codes()
        except Exception:
            logger.exception("Failed to refresh activation_codes_undelivered metric", extra={"event": "metrics_refresh_failed"})
            return
        self._metrics.set("activation_codes_undelivered", float(undelivered_count))

    def _compute_retry_delay_seconds(self, *, attempt: int) -> float:
        """Compute bounded exponential backoff with jitter."""
        raw_delay = self._retry_base_delay_seconds * (2 ** (attempt - 1))
        bounded_delay = min(self._retry_max_delay_seconds, raw_delay)
        jitter_span = bounded_delay * 0.2
        jitter = (secrets.randbelow(10_001) / 10_000 * 2 - 1) * jitter_span
        return max(0.0, bounded_delay + jitter)

    async def aclose(self) -> None:
        """Wait for in-flight background dispatch tasks to finish. Application shutdown"""
        if not self._background_tasks:
            return
        pending = list(self._background_tasks)
        await asyncio.gather(*pending, return_exceptions=True)
