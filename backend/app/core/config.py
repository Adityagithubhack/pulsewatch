from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PulseWatch API"
    database_url: str = "postgresql+asyncpg://pulsewatch:pulsewatch@postgres:5432/pulsewatch"
    redis_url: str = "redis://redis:6379/0"
    frontend_origin: str = "http://localhost:3001"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
