from pydantic import BaseModel, ConfigDict


class HeartbeatResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok"}})

    status: str
