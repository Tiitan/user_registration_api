import asyncio
import logging
import secrets
from time import perf_counter

import asyncmy

from api.app.config import get_settings
from api.app.db.transaction import transactional_cursor
from api.app.integrations import EmailProvider
from api.app.observability.metrics import MetricsRecorder, NoOpMetricsRecorder
from api.app.repositories import ActivationCodeRepository

logger = logging.getLogger(__name__)


class EmailDispatcher:
    def __init__(self, db_pool: asyncmy.Pool, email_provider: EmailProvider, *, metrics: MetricsRecorder | None = None, provider_name: str | None = None) -> None:
        settings = get_settings()
        self._db_pool = db_pool
        self._email_provider = email_provider
        self._provider_name = provider_name or email_provider.__class__.__name__.lower()
        self._metrics: MetricsRecorder = metrics or NoOpMetricsRecorder()
        self._max_retries = settings.email_provider_max_retries
        self._retry_base_delay_seconds = settings.email_provider_retry_base_delay_seconds
        self._retry_max_delay_seconds = settings.email_provider_retry_max_delay_seconds
        self._dispatch_semaphore = asyncio.Semaphore(settings.email_dispatch_max_concurrency)
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._activation_code_repository = ActivationCodeRepository()

    def dispatch_activation_email(self, *, user_id: int, activation_code_id: int, recipient_email: str, code: str) -> None:
        task = asyncio.create_task(
            self._run_dispatch(user_id=user_id, activation_code_id=activation_code_id, recipient_email=recipient_email, code=code)
        )
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
        async with self._dispatch_semaphore:
            tags = {"provider": self._provider_name}
            self._metrics.inc("dispatch_attempts_total", tags=tags)
            logger.info("Activation email dispatch started user_id=%s activation_code_id=%s",
                user_id, activation_code_id, extra={"event": "dispatch_attempt", "user_id": user_id, "activation_code_id": activation_code_id, "provider": self._provider_name})
            started = perf_counter()
            try:
                await self._email_provider.send_activation_email(recipient_email=recipient_email, code=code, user_id=user_id, activation_code_id=activation_code_id)
            except Exception as exc:
                duration_ms = (perf_counter() - started) * 1000
                self._metrics.observe("provider_latency_ms", duration_ms, tags=tags)
                error_type = exc.__class__.__name__
                self._metrics.inc("provider_errors_total", tags={"provider": self._provider_name, "error_type": error_type})
                self._metrics.inc("dispatch_terminal_failures_total", tags=tags)
                logger.exception(
                    "Activation email provider call failed user_id=%s activation_code_id=%s",
                    user_id,
                    activation_code_id,
                    extra={
                        "event": "dispatch_failure_terminal",
                        "user_id": user_id,
                        "activation_code_id": activation_code_id,
                        "provider": self._provider_name,
                        "error_type": error_type,
                        "duration_ms": round(duration_ms, 3),
                    },
                )
                await self._refresh_undelivered_activation_codes_metric()
                return

            duration_ms = (perf_counter() - started) * 1000
            self._metrics.observe("provider_latency_ms", duration_ms, tags=tags)

            sent_at_marked = await self._mark_activation_code_sent_with_retries(activation_code_id=activation_code_id, user_id=user_id)
            if sent_at_marked:
                self._metrics.inc("dispatch_successes_total", tags=tags)
                logger.info(
                    "Activation email delivered user_id=%s activation_code_id=%s",
                    user_id,
                    activation_code_id,
                    extra={
                        "event": "dispatch_success",
                        "user_id": user_id,
                        "activation_code_id": activation_code_id,
                        "provider": self._provider_name,
                        "duration_ms": round(duration_ms, 3),
                    },
                )
            else:
                self._metrics.inc("dispatch_terminal_failures_total", tags=tags)
                logger.error(
                    "Activation email was sent but sent_at update failed user_id=%s activation_code_id=%s",
                    user_id,
                    activation_code_id,
                    extra={
                        "event": "dispatch_failure_terminal",
                        "user_id": user_id,
                        "activation_code_id": activation_code_id,
                        "provider": self._provider_name,
                        "duration_ms": round(duration_ms, 3),
                    },
                )
            await self._refresh_undelivered_activation_codes_metric()

    async def _mark_activation_code_sent_with_retries(self, *, activation_code_id: int, user_id: int) -> bool:
        for attempt in range(1, self._max_retries + 1):
            try:
                await self._mark_activation_code_sent(activation_code_id=activation_code_id)
                return True
            except Exception as exc:
                final_attempt = attempt >= self._max_retries
                logger.warning(
                    "sent_at update failed user_id=%s activation_code_id=%s attempt=%s/%s error=%s",
                    user_id, activation_code_id, attempt, self._max_retries, str(exc),
                    extra={
                        "event": "dispatch_sent_at_retry",
                        "user_id": user_id,
                        "activation_code_id": activation_code_id,
                        "provider": self._provider_name,
                        "error_type": exc.__class__.__name__,
                    },
                )
                if final_attempt:
                    return False
                await asyncio.sleep(self._compute_retry_delay_seconds(attempt=attempt))
        return False

    async def _mark_activation_code_sent(self, *, activation_code_id: int) -> None:
        async with transactional_cursor(self._db_pool) as cursor:
            await self._activation_code_repository.mark_sent(cursor=cursor, activation_code_id=activation_code_id)

    async def _refresh_undelivered_activation_codes_metric(self) -> None:
        try:
            async with transactional_cursor(self._db_pool) as cursor:
                undelivered_count = await self._activation_code_repository.count_undelivered(cursor=cursor)
        except Exception:
            logger.exception("Failed to refresh activation_codes_undelivered metric", extra={"event": "metrics_refresh_failed"})
            return
        self._metrics.set("activation_codes_undelivered", float(undelivered_count))

    def _compute_retry_delay_seconds(self, *, attempt: int) -> float:
        raw_delay = self._retry_base_delay_seconds * (2 ** (attempt - 1))
        bounded_delay = min(self._retry_max_delay_seconds, raw_delay)
        jitter_span = bounded_delay * 0.2
        jitter = (secrets.randbelow(10_001) / 10_000 * 2 - 1) * jitter_span
        return max(0.0, bounded_delay + jitter)

    async def aclose(self) -> None:
        if not self._background_tasks:
            return
        pending = list(self._background_tasks)
        await asyncio.gather(*pending, return_exceptions=True)
