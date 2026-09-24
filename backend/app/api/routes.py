import uuid
from datetime import UTC, datetime, timedelta
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import CheckResult, CheckStatus, Endpoint, Incident
from app.schemas import (
    CheckRead,
    DashboardSummary,
    EndpointCreate,
    EndpointMetrics,
    EndpointRead,
    EndpointUpdate,
    IncidentRead,
)
from app.services.checks import execute_check

router = APIRouter(prefix="/api")


async def endpoint_with_latest(db: AsyncSession, endpoint: Endpoint) -> EndpointRead:
    latest = await db.scalar(
        select(CheckResult)
        .where(CheckResult.endpoint_id == endpoint.id)
        .order_by(CheckResult.checked_at.desc())
        .limit(1)
    )
    data = EndpointRead.model_validate(endpoint)
    return data.model_copy(update={"latest_check": CheckRead.model_validate(latest) if latest else None})


@router.get("/endpoints", response_model=list[EndpointRead])
async def list_endpoints(db: AsyncSession = Depends(get_db)) -> list[EndpointRead]:
    endpoints = (await db.scalars(select(Endpoint).order_by(Endpoint.created_at.desc()))).all()
    return [await endpoint_with_latest(db, endpoint) for endpoint in endpoints]


@router.post("/endpoints", response_model=EndpointRead, status_code=status.HTTP_201_CREATED)
async def create_endpoint(payload: EndpointCreate, db: AsyncSession = Depends(get_db)) -> EndpointRead:
    endpoint = Endpoint(**payload.model_dump())
    db.add(endpoint)
    await db.commit()
    await db.refresh(endpoint)
    return await endpoint_with_latest(db, endpoint)


@router.get("/endpoints/{endpoint_id}", response_model=EndpointRead)
async def get_endpoint(endpoint_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> EndpointRead:
    endpoint = await db.get(Endpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return await endpoint_with_latest(db, endpoint)


@router.patch("/endpoints/{endpoint_id}", response_model=EndpointRead)
async def update_endpoint(
    endpoint_id: uuid.UUID,
    payload: EndpointUpdate,
    db: AsyncSession = Depends(get_db),
) -> EndpointRead:
    endpoint = await db.get(Endpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(endpoint, field, value)
    await db.commit()
    await db.refresh(endpoint)
    return await endpoint_with_latest(db, endpoint)


@router.delete("/endpoints/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_endpoint(endpoint_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    result = await db.execute(delete(Endpoint).where(Endpoint.id == endpoint_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    await db.commit()


@router.post("/endpoints/{endpoint_id}/check", response_model=CheckRead)
async def check_now(endpoint_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> CheckRead:
    endpoint = await db.get(Endpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return CheckRead.model_validate(await execute_check(db, endpoint))


@router.get("/endpoints/{endpoint_id}/checks", response_model=list[CheckRead])
async def check_history(
    endpoint_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[CheckRead]:
    exists = await db.get(Endpoint, endpoint_id)
    if exists is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    checks = (
        await db.scalars(
            select(CheckResult)
            .where(CheckResult.endpoint_id == endpoint_id)
            .order_by(CheckResult.checked_at.desc())
            .limit(limit)
        )
    ).all()
    return [CheckRead.model_validate(check) for check in checks]


@router.get("/endpoints/{endpoint_id}/metrics", response_model=EndpointMetrics)
async def endpoint_metrics(
    endpoint_id: uuid.UUID,
    hours: int = Query(default=24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
) -> EndpointMetrics:
    endpoint = await db.get(Endpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    checks = (
        await db.scalars(
            select(CheckResult)
            .where(CheckResult.endpoint_id == endpoint_id, CheckResult.checked_at >= cutoff)
            .order_by(CheckResult.checked_at.asc())
        )
    ).all()
    successful = sum(check.status == CheckStatus.up for check in checks)
    latencies = sorted(
        check.latency_ms for check in checks if check.latency_ms is not None
    )
    p95_index = max(0, ceil(len(latencies) * 0.95) - 1) if latencies else 0
    incident_count = len(
        (
            await db.scalars(
                select(Incident).where(
                    Incident.endpoint_id == endpoint_id,
                    Incident.opened_at >= cutoff,
                )
            )
        ).all()
    )
    return EndpointMetrics(
        endpoint_id=endpoint_id,
        window_hours=hours,
        total_checks=len(checks),
        successful_checks=successful,
        uptime_percentage=round(successful / len(checks) * 100, 3) if checks else None,
        average_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else None,
        p95_latency_ms=round(latencies[p95_index], 2) if latencies else None,
        incident_count=incident_count,
        series=[CheckRead.model_validate(check) for check in checks[-200:]],
    )


@router.get("/incidents", response_model=list[IncidentRead])
async def list_incidents(
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[IncidentRead]:
    rows = (
        await db.execute(
            select(Incident, Endpoint)
            .join(Endpoint, Endpoint.id == Incident.endpoint_id)
            .order_by(Incident.opened_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        IncidentRead(
            id=incident.id,
            endpoint_id=incident.endpoint_id,
            endpoint_name=endpoint.name,
            endpoint_url=endpoint.url,
            opened_at=incident.opened_at,
            resolved_at=incident.resolved_at,
            opening_status_code=incident.opening_status_code,
            cause=incident.cause,
        )
        for incident, endpoint in rows
    ]


@router.get("/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary(db: AsyncSession = Depends(get_db)) -> DashboardSummary:
    endpoints = (await db.scalars(select(Endpoint))).all()
    up = down = paused = 0
    latencies: list[float] = []
    for endpoint in endpoints:
        if not endpoint.is_active:
            paused += 1
            continue
        latest = await db.scalar(
            select(CheckResult)
            .where(CheckResult.endpoint_id == endpoint.id)
            .order_by(CheckResult.checked_at.desc())
            .limit(1)
        )
        if latest and latest.status == CheckStatus.up:
            up += 1
            if latest.latency_ms is not None:
                latencies.append(latest.latency_ms)
        else:
            down += 1
    return DashboardSummary(
        total=len(endpoints),
        up=up,
        down=down,
        paused=paused,
        average_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else None,
    )
