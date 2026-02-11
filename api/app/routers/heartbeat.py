from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/heartbeat")
async def heartbeat() -> dict[str, str]:
    return {"status": "ok"}
