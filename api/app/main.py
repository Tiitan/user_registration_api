import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, cast

import asyncmy
from fastapi import FastAPI

from api.app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.db_pool = await _create_mysql_pool_with_retry()

    yield

    db_pool = app.state.db_pool
    if db_pool is not None:
        db_pool.close()
        await db_pool.wait_closed()


async def _create_mysql_pool_with_retry() -> asyncmy.Pool:
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

app = FastAPI(
    title="User Registration API",
    version="0.1.0",
    description="Dailymotion user registration test project.",
    lifespan=lifespan,
)


@app.get("/heartbeat", tags=["health"])
async def heartbeat() -> dict[str, str]:
    return {"status": "ok"}
