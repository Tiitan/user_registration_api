from typing import cast

import asyncmy
from fastapi import Request

from api.app.services.registration_service import RegistrationService


def get_db_pool(request: Request) -> asyncmy.Pool:
    return cast(asyncmy.Pool, request.app.state.db_pool)


def get_registration_service(request: Request) -> RegistrationService:
    return cast(RegistrationService, request.app.state.registration_service)
