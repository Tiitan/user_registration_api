from fastapi import APIRouter

from api.app.schemas.common import HeartbeatResponse

router = APIRouter(tags=["health"])


@router.get(
    "/heartbeat",
    response_model=HeartbeatResponse,
    summary="Service heartbeat",
    description="Lightweight liveness endpoint used by health checks and monitoring probes.",
    responses={200: {"description": "Service is healthy", "content": {"application/json": {"example": {"status": "ok"}}}}},
)
async def heartbeat() -> HeartbeatResponse:
    return HeartbeatResponse(status="ok")
