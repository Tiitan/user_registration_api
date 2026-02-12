"""MySQL connection pool creation utilities."""

import asyncio
import logging
from typing import cast

import asyncmy

from api.app.config import get_settings

logger = logging.getLogger(__name__)


async def create_mysql_pool_with_retry() -> asyncmy.Pool:
    """Create a MySQL pool with bounded retry attempts."""
    settings = get_settings()
    last_exception: Exception | None = None

    for attempt in range(1, settings.mysql_connect_retries + 1):
        try:
            pool = cast(
                asyncmy.Pool,
                await asyncmy.create_pool(
                    host=settings.mysql_host,
                    port=settings.mysql_port,
                    user=settings.mysql_user,
                    password=settings.mysql_password,
                    db=settings.mysql_database,
                    minsize=settings.mysql_pool_minsize,
                    maxsize=settings.mysql_pool_maxsize,
                    autocommit=True,
                ),
            )
            logger.info("MySQL pool created successfully on attempt %s/%s", attempt, settings.mysql_connect_retries)
            return pool
        except Exception as exc:
            last_exception = exc
            logger.warning("MySQL pool creation failed on attempt %s/%s: %s", attempt, settings.mysql_connect_retries, exc)
            await asyncio.sleep(settings.mysql_retry_delay_seconds)

    logger.error("Unable to connect to MySQL after %s attempts", settings.mysql_connect_retries)
    raise RuntimeError(f"Unable to connect to MySQL after {settings.mysql_connect_retries} attempts") from last_exception
