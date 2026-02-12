"""FastAPI dependency factories used by routers."""

from typing import cast

import asyncmy
from fastapi import Request

from api.app.observability.metrics import MetricsRecorder
from api.app.services.activation_service import ActivationService
from api.app.services.email_dispatcher import EmailDispatcher
from api.app.services.registration_service import RegistrationService


def get_db_pool(request: Request) -> asyncmy.Pool:
    """Return the initialized database pool from app state."""
    return cast(asyncmy.Pool, request.app.state.db_pool)


def get_email_dispatcher(request: Request) -> EmailDispatcher:
    """Return the email dispatcher from app state."""
    return cast(EmailDispatcher, request.app.state.email_dispatcher)


def get_metrics_recorder(request: Request) -> MetricsRecorder:
    """Return the metrics recorder from app state."""
    return cast(MetricsRecorder, request.app.state.metrics)


def get_registration_service(request: Request) -> RegistrationService:
    """Create a registration service with request-scoped dependencies."""
    return RegistrationService(db_pool=get_db_pool(request), email_dispatcher=get_email_dispatcher(request))


def get_activation_service(request: Request) -> ActivationService:
    """Create an activation service with request-scoped dependencies."""
    return ActivationService(db_pool=get_db_pool(request), email_dispatcher=get_email_dispatcher(request))
