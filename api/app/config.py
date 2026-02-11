from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_user: str = "app"
    mysql_password: str = "app"
    mysql_database: str = "user_registration"
    mysql_pool_minsize: int = 1
    mysql_pool_maxsize: int = 10
    mysql_connect_retries: int = 3
    mysql_retry_delay_seconds: float = 1.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
