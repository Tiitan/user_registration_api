"""Heartbeat endpoint router."""

import logging

import asyncmy
from fastapi import APIRouter, Depends, HTTPException, status

from api.app.dependencies import get_db_pool, get_email_provider
from api.app.integrations import EmailProvider
from api.app.schemas.common import HeartbeatResponse

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get(
    "/heartbeat",
    response_model=HeartbeatResponse,
    summary="Service heartbeat",
    description="Lightweight liveness endpoint used by health checks and monitoring probes.",
    responses={200: {"description": "Service is healthy", "content": {"application/json": {"example": {"status": "ok"}}}}},
)
async def heartbeat() -> HeartbeatResponse:
    """Return service liveness status."""
    return HeartbeatResponse(status="ok")


@router.get(
    "/readiness",
    response_model=HeartbeatResponse,
    summary="Service readiness",
    description="Readiness endpoint that validates database and email provider connectivity.",
    responses={
        200: {"description": "Service is ready to receive traffic", "content": {"application/json": {"example": {"status": "ok"}}}},
        503: {"description": "Service is not ready to receive traffic"},
    },
)
async def readiness(db_pool: asyncmy.Pool = Depends(get_db_pool), email_provider: EmailProvider = Depends(get_email_provider)) -> HeartbeatResponse:
    """Return readiness status after verifying DB and provider connectivity."""
    try:
        async with db_pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT 1")
    except Exception as exc:
        logger.warning("Readiness probe failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable") from exc
    try:
        await email_provider.probe()
    except Exception as exc:
        logger.warning("Readiness email provider probe failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="email provider unavailable") from exc
    return HeartbeatResponse(status="ok")
