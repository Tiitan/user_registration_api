"""FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.app.config import get_settings
from api.app.exceptions import register_exception_handlers
from api.app.lifespan import lifespan
from api.app.logging_config import configure_logging
from api.app.observability import RequestContextMiddleware
from api.app.routers import heartbeat_router, observability_router, users_router

configure_logging()
settings = get_settings()


app = FastAPI(
    title="User Registration API",
    version="0.1.0",
    description=(
        "API for user registration and activation.\n\n"
        "Main flows:\n"
        "- `POST /v1/users` creates or resets a pending user and schedules activation code delivery.\n"
        "- `POST /v1/users/activate` activates account with Basic Auth + 4-digit code.\n"
        "- `GET /heartbeat` is the service liveness endpoint."
    ),
    lifespan=lifespan,
    contact={"name": "API Team"},
    openapi_tags=[
        {"name": "users", "description": "User registration and activation endpoints."},
        {"name": "health", "description": "Operational health endpoints."},
    ],
)

register_exception_handlers(app)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods_list,
    allow_headers=settings.cors_allow_headers_list,
)
app.include_router(users_router)
app.include_router(heartbeat_router)
app.include_router(observability_router)
