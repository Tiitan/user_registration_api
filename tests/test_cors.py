"""Tests for CORS configuration."""

from fastapi.middleware.cors import CORSMiddleware

from api.app.config import Settings
from api.app.main import app


def test_settings_parse_cors_csv_values() -> None:
    """Parses comma-separated CORS settings into normalized lists."""
    settings = Settings(
        cors_allow_origins="https://frontend.example, http://localhost:5173",
        cors_allow_methods="GET, POST, OPTIONS",
        cors_allow_headers="Authorization, Content-Type",
    )

    assert settings.cors_allow_origins_list == ["https://frontend.example", "http://localhost:5173"]
    assert settings.cors_allow_methods_list == ["GET", "POST", "OPTIONS"]
    assert settings.cors_allow_headers_list == ["Authorization", "Content-Type"]


def test_main_app_registers_cors_middleware() -> None:
    """Registers CORSMiddleware on the main application."""
    cors_middleware = next((middleware for middleware in app.user_middleware if middleware.cls is CORSMiddleware), None)

    assert cors_middleware is not None
    assert "http://localhost:3000" in cors_middleware.kwargs["allow_origins"]
    assert cors_middleware.kwargs["allow_credentials"] is True
