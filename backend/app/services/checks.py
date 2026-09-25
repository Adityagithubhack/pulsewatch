import json
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import CheckResult, CheckStatus, Endpoint, Incident, MaintenanceWindow
from app.services.audit import record_audit
from app.services.monitor import probe_url
from app.services.notifications import send_alert


async def execute_check(db: AsyncSession, endpoint: Endpoint) -> CheckResult:
    recent = (
        await db.scalars(
            select(CheckResult)
            .where(CheckResult.endpoint_id == endpoint.id)
            .order_by(CheckResult.checked_at.desc())
            .limit(max(endpoint.failure_threshold, endpoint.recovery_threshold, 1))
        )
    ).all()
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
        region=settings.probe_region,
    )
    db.add(result)
    await db.flush()

    now = datetime.now(UTC)
    maintenance_active = await db.scalar(
        select(MaintenanceWindow.id)
        .where(
            MaintenanceWindow.starts_at <= now,
            MaintenanceWindow.ends_at >= now,
            (MaintenanceWindow.endpoint_id.is_(None))
            | (MaintenanceWindow.endpoint_id == endpoint.id),
        )
        .limit(1)
    )
    active_incident = await db.scalar(
        select(Incident)
        .where(Incident.endpoint_id == endpoint.id, Incident.resolved_at.is_(None))
        .order_by(Incident.opened_at.desc())
        .limit(1)
    )

    previous_failures = 0
    for check in recent:
        if check.status == CheckStatus.down and check.status_code not in {403, 429}:
            previous_failures += 1
        else:
            break
    confirmed_failure = (
        probe.availability == "down"
        and previous_failures + 1 >= endpoint.failure_threshold
        and active_incident is None
        and maintenance_active is None
    )

    previous_recoveries = 0
    for check in recent:
        if check.status == CheckStatus.up or check.status_code in {403, 429}:
            previous_recoveries += 1
        else:
            break
    confirmed_recovery = (
        probe.availability in {"up", "blocked"}
        and previous_recoveries + 1 >= endpoint.recovery_threshold
        and active_incident is not None
        and maintenance_active is None
    )

    alert_event: tuple[str, str] | None = None
    if confirmed_failure:
        incident = Incident(
            endpoint_id=endpoint.id,
            opening_status_code=result.status_code,
            cause=result.error,
        )
        db.add(incident)
        await db.flush()
        await record_audit(
            db,
            "incident.opened",
            "incident",
            incident.id,
            f"{endpoint.name}: {result.error}",
        )
        alert_event = ("incident", result.error or "Health check failed")
    elif confirmed_recovery and active_incident is not None:
        active_incident.resolved_at = now
        await record_audit(
            db,
            "incident.resolved",
            "incident",
            active_incident.id,
            f"{endpoint.name} recovered",
            actor="system",
        )
        alert_event = ("recovery", f"Service recovered with HTTP {result.status_code}")

    await db.commit()
    await db.refresh(result)

    if alert_event is not None:
        await send_alert(alert_event[0], endpoint.name, alert_event[1])

    payload = {
        "endpoint_id": str(endpoint.id),
        "name": endpoint.name,
        "status": result.status.value,
        "availability": probe.availability,
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


async def execute_check_by_id(
    db: AsyncSession, endpoint_id: uuid.UUID
) -> CheckResult | None:
    endpoint = await db.get(Endpoint, endpoint_id)
    if endpoint is None:
        return None
    return await execute_check(db, endpoint)
