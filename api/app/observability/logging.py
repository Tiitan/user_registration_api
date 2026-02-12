from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from api.app.observability.request_context import get_correlation_id, get_request_id


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        record.correlation_id = get_correlation_id()
        if not hasattr(record, "event"):
            record.event = "log"
        for field in (
            "user_id",
            "activation_code_id",
            "provider",
            "error_type",
            "error_code",
            "duration_ms",
            "status_code",
            "http_method",
            "path",
        ):
            if not hasattr(record, field):
                setattr(record, field, None)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", "log"),
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "correlation_id": getattr(record, "correlation_id", "-"),
            "user_id": getattr(record, "user_id", None),
            "activation_code_id": getattr(record, "activation_code_id", None),
            "provider": getattr(record, "provider", None),
            "error_type": getattr(record, "error_type", None),
            "error_code": getattr(record, "error_code", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "status_code": getattr(record, "status_code", None),
            "http_method": getattr(record, "http_method", None),
            "path": getattr(record, "path", None),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
