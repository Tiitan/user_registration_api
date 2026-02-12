from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
