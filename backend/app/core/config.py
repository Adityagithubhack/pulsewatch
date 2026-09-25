from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PulseWatch API"
    database_url: str = (
        "postgresql+asyncpg://pulsewatch:pulsewatch@postgres:5432/pulsewatch"
    )
    redis_url: str = "redis://redis:6379/0"
    frontend_origin: str = "http://localhost:3001"
    public_base_url: str = "http://localhost:3001"
    probe_region: str = "local"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    alert_webhook_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    alert_email_from: str | None = None
    alert_email_to: str | None = None
    auth_enabled: bool = False
    admin_email: str | None = None
    admin_password: str | None = None
    session_ttl_hours: int = 24

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
