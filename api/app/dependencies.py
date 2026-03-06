"""FastAPI dependency factories used by routers."""

from typing import cast

import asyncmy
from fastapi import Request

from api.app.integrations import EmailProvider
from api.app.observability import MetricsRecorder
from api.app.services import ActivationService, EmailDispatcher, RegistrationService
from api.app.unit_of_work import UnitOfWorkFactory


def get_db_pool(request: Request) -> asyncmy.Pool:
    """Return the initialized database pool from app state."""
    return cast(asyncmy.Pool, request.app.state.db_pool)


def get_uow_factory(request: Request) -> UnitOfWorkFactory:
    """Return the initialized unit of work factory from app state."""
    return cast(UnitOfWorkFactory, request.app.state.uow_factory)


def get_email_dispatcher(request: Request) -> EmailDispatcher:
    """Return the email dispatcher from app state."""
    return cast(EmailDispatcher, request.app.state.email_dispatcher)


def get_email_provider(request: Request) -> EmailProvider:
    """Return the email provider from app state."""
    return cast(EmailProvider, request.app.state.email_provider)


def get_metrics_recorder(request: Request) -> MetricsRecorder:
    """Return the metrics recorder from app state."""
    return cast(MetricsRecorder, request.app.state.metrics)


def get_registration_service(request: Request) -> RegistrationService:
    """Create a registration service with request-scoped dependencies."""
    return RegistrationService(uow_factory=get_uow_factory(request), email_dispatcher=get_email_dispatcher(request))


def get_activation_service(request: Request) -> ActivationService:
    """Create an activation service with request-scoped dependencies."""
    return ActivationService(uow_factory=get_uow_factory(request), email_dispatcher=get_email_dispatcher(request))
