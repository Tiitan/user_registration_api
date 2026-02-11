from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from api.app.db.pool import create_mysql_pool_with_retry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.db_pool = await create_mysql_pool_with_retry()

    yield

    db_pool = app.state.db_pool
    if db_pool is not None:
        db_pool.close()
        await db_pool.wait_closed()
