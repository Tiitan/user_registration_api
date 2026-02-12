"""Configuration loading for runtime settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings sourced from environment variables."""

    log_level: str = "INFO"
    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_user: str = "app"
    mysql_password: str = "app"
    mysql_database: str = "user_registration"
    mysql_pool_minsize: int = 1
    mysql_pool_maxsize: int = 10
    mysql_connect_retries: int = 3
    mysql_retry_delay_seconds: float = 1.0
    email_provider_max_retries: int = 3
    email_provider_retry_base_delay_seconds: float = 1.0
    email_provider_retry_max_delay_seconds: float = 8.0
    email_dispatch_max_concurrency: int = 50
    activation_code_ttl_seconds: int = 60
    activation_code_max_attempts: int = 5
    cors_allow_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "*"
    cors_allow_headers: str = "*"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", case_sensitive=False)

    @staticmethod
    def _split_csv(value: str) -> list[str]:
        """Split a comma-separated config value into a normalized list."""
        return [item.strip() for item in value.split(",") if item.strip()]

    @property
    def cors_allow_origins_list(self) -> list[str]:
        """Return CORS allowed origins as a list."""
        return self._split_csv(self.cors_allow_origins)

    @property
    def cors_allow_methods_list(self) -> list[str]:
        """Return CORS allowed methods as a list."""
        return self._split_csv(self.cors_allow_methods)

    @property
    def cors_allow_headers_list(self) -> list[str]:
        """Return CORS allowed headers as a list."""
        return self._split_csv(self.cors_allow_headers)


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()
