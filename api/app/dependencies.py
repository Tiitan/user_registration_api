from typing import cast

import asyncmy
from fastapi import Depends, Request

from api.app.services.registration_service import RegistrationService


def get_db_pool(request: Request) -> asyncmy.Pool:
    return cast(asyncmy.Pool, request.app.state.db_pool)


def get_registration_service(db_pool: asyncmy.Pool = Depends(get_db_pool)) -> RegistrationService:
    return RegistrationService(db_pool=db_pool)
