from contextlib import asynccontextmanager
import logging
from typing import AsyncIterator

from fastapi import FastAPI

from api.app.db.pool import create_mysql_pool_with_retry
from api.app.services.email_dispatcher import EmailDispatcher
from api.app.services.registration_service import RegistrationService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting application lifespan")
    app.state.db_pool = await create_mysql_pool_with_retry()
    app.state.email_dispatcher = EmailDispatcher(db_pool=app.state.db_pool)
    app.state.registration_service = RegistrationService(db_pool=app.state.db_pool, email_dispatcher=app.state.email_dispatcher)
    logger.info("Application resources initialized")

    yield

    db_pool = app.state.db_pool
    email_dispatcher = app.state.email_dispatcher
    app.state.email_dispatcher = None
    app.state.registration_service = None
    logger.info("Shutting down application resources")
    if email_dispatcher is not None:
        await email_dispatcher.aclose()
    if db_pool is not None:
        db_pool.close()
        await db_pool.wait_closed()
    logger.info("Application shutdown complete")
