import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, cast

import asyncmy
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.db_pool = await _create_mysql_pool_with_retry()

    yield

    db_pool = app.state.db_pool
    if db_pool is not None:
        db_pool.close()
        await db_pool.wait_closed()


async def _create_mysql_pool_with_retry() -> asyncmy.Pool:
    host = os.getenv("MYSQL_HOST", "mysql")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "app")
    password = os.getenv("MYSQL_PASSWORD", "app")
    database = os.getenv("MYSQL_DATABASE", "user_registration")

    last_exception: Exception | None = None

    for _ in range(30):
        try:
            return cast(
                asyncmy.Pool,
                await asyncmy.create_pool(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    db=database,
                    minsize=1,
                    maxsize=10,
                    autocommit=True,
                ),
            )
        except Exception as exc:
            last_exception = exc
            await asyncio.sleep(1)

    raise RuntimeError("Unable to connect to MySQL after 30 attempts") from last_exception

app = FastAPI(
    title="User Registration API",
    version="0.1.0",
    description="Dailymotion user registration test project.",
    lifespan=lifespan,
)


@app.get("/heartbeat", tags=["health"])
async def heartbeat() -> dict[str, str]:
    return {"status": "ok"}
