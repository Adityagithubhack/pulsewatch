import json
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import CheckResult, CheckStatus, Endpoint, Incident
from app.services.monitor import probe_url


async def execute_check(db: AsyncSession, endpoint: Endpoint) -> CheckResult:
    previous = await db.scalar(
        select(CheckResult)
        .where(CheckResult.endpoint_id == endpoint.id)
        .order_by(CheckResult.checked_at.desc())
        .limit(1)
    )
    probe = await probe_url(
        endpoint.url,
        endpoint.method,
        endpoint.expected_status,
        endpoint.timeout_seconds,
    )
    result = CheckResult(
        endpoint_id=endpoint.id,
        status=CheckStatus.up if probe.is_up else CheckStatus.down,
        status_code=probe.status_code,
        latency_ms=probe.latency_ms,
        error=probe.error,
    )
    db.add(result)
    await db.flush()

    changed_to_down = result.status == CheckStatus.down and (
        previous is None or previous.status != CheckStatus.down
    )
    recovered = result.status == CheckStatus.up and previous is not None and previous.status == CheckStatus.down
    if changed_to_down:
        db.add(
            Incident(
                endpoint_id=endpoint.id,
                opening_status_code=result.status_code,
                cause=result.error,
            )
        )
    elif recovered:
        incident = await db.scalar(
            select(Incident)
            .where(Incident.endpoint_id == endpoint.id, Incident.resolved_at.is_(None))
            .order_by(Incident.opened_at.desc())
            .limit(1)
        )
        if incident is not None:
            incident.resolved_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(result)

    payload = {
        "endpoint_id": str(endpoint.id),
        "name": endpoint.name,
        "status": result.status.value,
        "status_code": result.status_code,
        "latency_ms": result.latency_ms,
        "checked_at": result.checked_at.isoformat(),
    }
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.publish("pulsewatch:checks", json.dumps(payload))
    finally:
        await redis.aclose()

    return result


async def execute_check_by_id(db: AsyncSession, endpoint_id: uuid.UUID) -> CheckResult | None:
    endpoint = await db.get(Endpoint, endpoint_id)
    if endpoint is None:
        return None
    return await execute_check(db, endpoint)
