from contextlib import asynccontextmanager
import logging
from typing import AsyncIterator

from fastapi import FastAPI

from api.app.db.pool import create_mysql_pool_with_retry
from api.app.integrations import MockEmailProvider
from api.app.services.email_dispatcher import EmailDispatcher

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting application lifespan")
    db_pool = await create_mysql_pool_with_retry()
    email_provider = MockEmailProvider()
    email_dispatcher = EmailDispatcher(db_pool=db_pool, email_provider=email_provider)
    app.state.db_pool = db_pool
    app.state.email_provider = email_provider
    app.state.email_dispatcher = email_dispatcher
    logger.info("Application resources initialized")

    yield
    
    db_pool = getattr(app.state, "db_pool", None)
    email_dispatcher = getattr(app.state, "email_dispatcher", None)
    app.state.email_provider = None
    app.state.email_dispatcher = None
    logger.info("Shutting down application resources")
    if email_dispatcher is not None:
        await email_dispatcher.aclose()
    if db_pool is not None:
        db_pool.close()
        await db_pool.wait_closed()
    logger.info("Application shutdown complete")
