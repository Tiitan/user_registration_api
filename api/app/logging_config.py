import logging.config

from api.app.config import get_settings


def configure_logging() -> None:
    log_level = get_settings().log_level.upper()

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "request_context": {
                    "()": "api.app.observability.logging.RequestContextFilter",
                }
            },
            "formatters": {
                "json": {
                    "()": "api.app.observability.logging.JsonFormatter",
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "filters": ["request_context"],
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {
                "handlers": ["default"],
                "level": log_level,
            },
            "loggers": {
                "uvicorn": {
                    "handlers": ["default"],
                    "level": log_level,
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["default"],
                    "level": log_level,
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": ["default"],
                    "level": log_level,
                    "propagate": False,
                },
                "api": {
                    "handlers": ["default"],
                    "level": log_level,
                    "propagate": False,
                },
            },
        }
    )
