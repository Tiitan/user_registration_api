import asyncio
import logging
import secrets

import asyncmy
from asyncmy.cursors import DictCursor

from api.app.config import get_settings

logger = logging.getLogger(__name__)


class EmailDispatcher:
    def __init__(self, db_pool: asyncmy.Pool) -> None:
        settings = get_settings()
        self._db_pool = db_pool
        self._max_retries = settings.email_provider_max_retries
        self._retry_base_delay_seconds = settings.email_provider_retry_base_delay_seconds
        self._retry_max_delay_seconds = settings.email_provider_retry_max_delay_seconds
        self._dispatch_semaphore = asyncio.Semaphore(settings.email_dispatch_max_concurrency)
        self._background_tasks: set[asyncio.Task[None]] = set()

    def dispatch_activation_email(self, *, user_id: int, activation_code_id: int, recipient_email: str, code: str) -> None:
        task = asyncio.create_task(
            self._run_dispatch(
                user_id=user_id,
                activation_code_id=activation_code_id,
                recipient_email=recipient_email,
                code=code,
            )
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
            await self._send_activation_email(
                recipient_email=recipient_email,
                code=code,
                user_id=user_id,
                activation_code_id=activation_code_id,
            )
            sent_at_marked = await self._mark_activation_code_sent_with_retries(
                activation_code_id=activation_code_id,
                user_id=user_id,
            )
            if sent_at_marked:
                logger.info("Activation email delivered user_id=%s activation_code_id=%s", user_id, activation_code_id)
            else:
                logger.error("Activation email was simulated as sent but sent_at update failed user_id=%s activation_code_id=%s",
                    user_id, activation_code_id)

    async def _send_activation_email(self, *, recipient_email: str, code: str, user_id: int, activation_code_id: int) -> None:
        # Mock of a third-party SMTP-over-HTTP provider call as allowed by specs.
        logger.info("Simulated email provider HTTP request to=%s user_id=%s activation_code_id=%s code=%s",
            recipient_email, user_id, activation_code_id, code)
        await asyncio.sleep(0)

    async def _mark_activation_code_sent_with_retries(self, *, activation_code_id: int, user_id: int) -> bool:
        for attempt in range(1, self._max_retries + 1):
            try:
                await self._mark_activation_code_sent(activation_code_id=activation_code_id)
                return True
            except Exception as exc:
                final_attempt = attempt >= self._max_retries
                logger.warning("sent_at update failed user_id=%s activation_code_id=%s attempt=%s/%s error=%s",
                    user_id, activation_code_id, attempt, self._max_retries, str(exc))
                if final_attempt:
                    return False
                await asyncio.sleep(self._compute_retry_delay_seconds(attempt=attempt))
        return False

    async def _mark_activation_code_sent(self, *, activation_code_id: int) -> None:
        async with self._db_pool.acquire() as connection:
            await connection.begin()
            try:
                async with connection.cursor(DictCursor) as cursor:
                    await cursor.execute("UPDATE activation_codes SET sent_at = CURRENT_TIMESTAMP(6) WHERE id = %s AND sent_at IS NULL",
                        (activation_code_id,))
                await connection.commit()
            except Exception:
                await connection.rollback()
                raise

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
