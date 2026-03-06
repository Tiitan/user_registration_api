"""Application lifespan hooks for startup and shutdown resources."""

from contextlib import asynccontextmanager
import logging
from typing import AsyncIterator

from fastapi import FastAPI

from api.app.db import MySqlUnitOfWorkFactory, create_mysql_pool_with_retry
from api.app.integrations import MockEmailProvider
from api.app.observability import InMemoryMetricsRecorder
from api.app.services import EmailDispatcher

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize and clean up shared app resources."""
    logger.info("Starting application lifespan")
    db_pool = await create_mysql_pool_with_retry()
    uow_factory = MySqlUnitOfWorkFactory(db_pool)
    email_provider = MockEmailProvider()
    metrics = InMemoryMetricsRecorder()
    dispatcher = EmailDispatcher(uow_factory=uow_factory, email_provider=email_provider, metrics=metrics, provider_name="mock_email_provider")
    app.state.db_pool = db_pool
    app.state.uow_factory = uow_factory
    app.state.email_provider = email_provider
    app.state.email_dispatcher = dispatcher
    app.state.metrics = metrics
    logger.info("Application resources initialized")

    yield

    shutdown_pool = getattr(app.state, "db_pool", None)
    shutdown_dispatcher = getattr(app.state, "email_dispatcher", None)
    app.state.uow_factory = None
    app.state.email_provider = None
    app.state.email_dispatcher = None
    app.state.metrics = None
    logger.info("Shutting down application resources")
    if isinstance(shutdown_dispatcher, EmailDispatcher):
        await shutdown_dispatcher.aclose()
    if shutdown_pool is not None:
        shutdown_pool.close()
        await shutdown_pool.wait_closed()
    logger.info("Application shutdown complete")
