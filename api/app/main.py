from fastapi import FastAPI

from api.app.db.lifespan import lifespan
from api.app.routers import heartbeat_router, users_router


app = FastAPI(
    title="User Registration API",
    version="0.1.0",
    description="Dailymotion user registration test project.",
    lifespan=lifespan,
)

app.include_router(users_router)
app.include_router(heartbeat_router)
