from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def create_schema() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        # Backward-compatible additions for databases created by PulseWatch v1-v3.
        # PostgreSQL's IF NOT EXISTS keeps startup idempotent while preserving all data.
        statements = [
            "ALTER TABLE endpoints ADD COLUMN IF NOT EXISTS failure_threshold INTEGER NOT NULL DEFAULT 2",
            "ALTER TABLE endpoints ADD COLUMN IF NOT EXISTS recovery_threshold INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE endpoints ADD COLUMN IF NOT EXISTS ssl_expiry_enabled BOOLEAN NOT NULL DEFAULT true",
            "ALTER TABLE check_results ADD COLUMN IF NOT EXISTS region VARCHAR(80) NOT NULL DEFAULT 'local'",
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS severity VARCHAR(20) NOT NULL DEFAULT 'critical'",
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ NULL",
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS acknowledged_by VARCHAR(120) NULL",
            "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS notes TEXT NULL",
        ]
        for statement in statements:
            await connection.execute(text(statement))
