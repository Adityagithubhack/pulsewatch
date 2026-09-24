import asyncio
import uuid
from datetime import UTC, datetime

from celery import Celery
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import CheckResult, Endpoint
from app.services.checks import execute_check_by_id

celery_app = Celery("pulsewatch", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.beat_schedule = {
    "schedule-due-endpoints": {
        "task": "pulsewatch.schedule_due_endpoints",
        "schedule": 30.0,
    }
}
celery_app.conf.timezone = "UTC"


async def _check_endpoint(endpoint_id: str) -> None:
    async with SessionLocal() as db:
        await execute_check_by_id(db, uuid.UUID(endpoint_id))


@celery_app.task(name="pulsewatch.check_endpoint")
def check_endpoint_task(endpoint_id: str) -> None:
    asyncio.run(_check_endpoint(endpoint_id))


async def _schedule_due() -> list[str]:
    due: list[str] = []
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        endpoints = (await db.scalars(select(Endpoint).where(Endpoint.is_active.is_(True)))).all()
        for endpoint in endpoints:
            latest = await db.scalar(
                select(CheckResult)
                .where(CheckResult.endpoint_id == endpoint.id)
                .order_by(CheckResult.checked_at.desc())
                .limit(1)
            )
            if latest is None or (now - latest.checked_at).total_seconds() >= endpoint.interval_seconds:
                due.append(str(endpoint.id))
    return due


@celery_app.task(name="pulsewatch.schedule_due_endpoints")
def schedule_due_endpoints() -> int:
    due = asyncio.run(_schedule_due())
    for endpoint_id in due:
        check_endpoint_task.delay(endpoint_id)
    return len(due)
