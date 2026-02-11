import asyncio
from typing import cast

import asyncmy

from api.app.config import get_settings


async def create_mysql_pool_with_retry() -> asyncmy.Pool:
    settings = get_settings()
    last_exception: Exception | None = None

    for _ in range(settings.mysql_connect_retries):
        try:
            return cast(
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
        except Exception as exc:
            last_exception = exc
            await asyncio.sleep(settings.mysql_retry_delay_seconds)

    raise RuntimeError(
        f"Unable to connect to MySQL after {settings.mysql_connect_retries} attempts"
    ) from last_exception
