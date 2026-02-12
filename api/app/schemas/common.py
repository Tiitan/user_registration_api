"""Common API response schemas."""

from pydantic import BaseModel, ConfigDict


class HeartbeatResponse(BaseModel):
    """Liveness response payload."""

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok"}})

    status: str
