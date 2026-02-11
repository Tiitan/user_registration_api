from fastapi import FastAPI

from api.app.db.lifespan import lifespan
from api.app.logging_config import configure_logging
from api.app.routers import heartbeat_router, users_router

configure_logging()


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

app.include_router(users_router)
app.include_router(heartbeat_router)
