import uuid
from datetime import UTC, datetime, timedelta
from math import ceil

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models import (
    AuditLog,
    CheckResult,
    CheckStatus,
    Endpoint,
    Incident,
    MaintenanceWindow,
    Operator,
    OperatorSession,
)
from app.schemas import (
    AuditLogRead,
    AuthStatus,
    CheckRead,
    DashboardSummary,
    DiagnosticsRead,
    EndpointCreate,
    EndpointMetrics,
    EndpointRead,
    EndpointUpdate,
    IncidentRead,
    IncidentUpdate,
    LoginRequest,
    MaintenanceCreate,
    MaintenanceRead,
    NotificationStatus,
)
from app.services.audit import record_audit
from app.services.auth import (
    authenticate_session,
    create_session,
    require_operator,
    token_digest,
    verify_password,
)
from app.services.checks import execute_check
from app.services.diagnostics import inspect_endpoint
from app.services.notifications import notification_status

router = APIRouter(prefix="/api")


@router.get("/auth/status", response_model=AuthStatus)
async def auth_status(
    operator: Operator | None = Depends(authenticate_session),
) -> AuthStatus:
    return AuthStatus(
        enabled=settings.auth_enabled,
        authenticated=operator is not None or not settings.auth_enabled,
        email=operator.email if operator else None,
        role=operator.role
        if operator
        else ("local" if not settings.auth_enabled else None),
    )


@router.post("/auth/login", response_model=AuthStatus)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthStatus:
    if not settings.auth_enabled:
        return AuthStatus(enabled=False, authenticated=True, role="local")
    operator = await db.scalar(
        select(Operator).where(Operator.email == payload.email.lower())
    )
    if (
        operator is None
        or not operator.is_active
        or not verify_password(payload.password, operator.password_hash)
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token, expires_at = await create_session(db, operator)
    response.set_cookie(
        "pulsewatch_session",
        token,
        httponly=True,
        secure=settings.public_base_url.startswith("https://"),
        samesite="lax",
        expires=expires_at,
    )
    return AuthStatus(
        enabled=True, authenticated=True, email=operator.email, role=operator.role
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    pulsewatch_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> None:
    if pulsewatch_session:
        await db.execute(
            delete(OperatorSession).where(
                OperatorSession.token_hash == token_digest(pulsewatch_session)
            )
        )
        await db.commit()
    response.delete_cookie("pulsewatch_session")


async def endpoint_with_latest(db: AsyncSession, endpoint: Endpoint) -> EndpointRead:
    latest = await db.scalar(
        select(CheckResult)
        .where(CheckResult.endpoint_id == endpoint.id)
        .order_by(CheckResult.checked_at.desc())
        .limit(1)
    )
    data = EndpointRead.model_validate(endpoint)
    return data.model_copy(
        update={"latest_check": CheckRead.model_validate(latest) if latest else None}
    )


@router.get("/endpoints", response_model=list[EndpointRead])
async def list_endpoints(db: AsyncSession = Depends(get_db)) -> list[EndpointRead]:
    endpoints = (
        await db.scalars(select(Endpoint).order_by(Endpoint.created_at.desc()))
    ).all()
    return [await endpoint_with_latest(db, endpoint) for endpoint in endpoints]


@router.post(
    "/endpoints", response_model=EndpointRead, status_code=status.HTTP_201_CREATED
)
async def create_endpoint(
    payload: EndpointCreate,
    db: AsyncSession = Depends(get_db),
    _operator: Operator | None = Depends(require_operator),
) -> EndpointRead:
    endpoint = Endpoint(**payload.model_dump())
    db.add(endpoint)
    await db.flush()
    await record_audit(db, "monitor.created", "endpoint", endpoint.id, payload.name)
    await db.commit()
    await db.refresh(endpoint)
    return await endpoint_with_latest(db, endpoint)


@router.get("/endpoints/{endpoint_id}", response_model=EndpointRead)
async def get_endpoint(
    endpoint_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> EndpointRead:
    endpoint = await db.get(Endpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return await endpoint_with_latest(db, endpoint)


@router.patch("/endpoints/{endpoint_id}", response_model=EndpointRead)
async def update_endpoint(
    endpoint_id: uuid.UUID,
    payload: EndpointUpdate,
    db: AsyncSession = Depends(get_db),
    _operator: Operator | None = Depends(require_operator),
) -> EndpointRead:
    endpoint = await db.get(Endpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(endpoint, field, value)
    await record_audit(
        db,
        "monitor.updated",
        "endpoint",
        endpoint.id,
        str(payload.model_dump(exclude_unset=True)),
    )
    await db.commit()
    await db.refresh(endpoint)
    return await endpoint_with_latest(db, endpoint)


@router.delete("/endpoints/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_endpoint(
    endpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _operator: Operator | None = Depends(require_operator),
) -> None:
    result = await db.execute(delete(Endpoint).where(Endpoint.id == endpoint_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    await record_audit(db, "monitor.deleted", "endpoint", endpoint_id)
    await db.commit()


@router.post("/endpoints/{endpoint_id}/check", response_model=CheckRead)
async def check_now(
    endpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _operator: Operator | None = Depends(require_operator),
) -> CheckRead:
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
            .where(
                CheckResult.endpoint_id == endpoint_id, CheckResult.checked_at >= cutoff
            )
            .order_by(CheckResult.checked_at.asc())
        )
    ).all()
    availability_checks = [
        check for check in checks if check.status_code not in {403, 429}
    ]
    successful = sum(check.status == CheckStatus.up for check in availability_checks)
    latencies = sorted(
        check.latency_ms
        for check in availability_checks
        if check.latency_ms is not None
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
        uptime_percentage=(
            round(successful / len(availability_checks) * 100, 3)
            if availability_checks
            else None
        ),
        average_latency_ms=round(sum(latencies) / len(latencies), 2)
        if latencies
        else None,
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
            severity=incident.severity,
            acknowledged_at=incident.acknowledged_at,
            acknowledged_by=incident.acknowledged_by,
            notes=incident.notes,
        )
        for incident, endpoint in rows
    ]


@router.patch("/incidents/{incident_id}", response_model=IncidentRead)
async def update_incident(
    incident_id: uuid.UUID,
    payload: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    _operator: Operator | None = Depends(require_operator),
) -> IncidentRead:
    incident = await db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    endpoint = await db.get(Endpoint, incident.endpoint_id)
    if payload.acknowledged_by:
        incident.acknowledged_at = datetime.now(UTC)
        incident.acknowledged_by = payload.acknowledged_by
    if payload.notes is not None:
        incident.notes = payload.notes
    if payload.resolve and incident.resolved_at is None:
        incident.resolved_at = datetime.now(UTC)
    await record_audit(
        db,
        "incident.updated",
        "incident",
        incident.id,
        str(payload.model_dump(exclude_unset=True)),
    )
    await db.commit()
    await db.refresh(incident)
    return IncidentRead(
        id=incident.id,
        endpoint_id=incident.endpoint_id,
        endpoint_name=endpoint.name if endpoint else "Deleted service",
        endpoint_url=endpoint.url if endpoint else "",
        opened_at=incident.opened_at,
        resolved_at=incident.resolved_at,
        opening_status_code=incident.opening_status_code,
        cause=incident.cause,
        severity=incident.severity,
        acknowledged_at=incident.acknowledged_at,
        acknowledged_by=incident.acknowledged_by,
        notes=incident.notes,
    )


@router.get("/maintenance", response_model=list[MaintenanceRead])
async def list_maintenance(
    db: AsyncSession = Depends(get_db),
) -> list[MaintenanceWindow]:
    return list(
        (
            await db.scalars(
                select(MaintenanceWindow).order_by(MaintenanceWindow.starts_at.desc())
            )
        ).all()
    )


@router.post(
    "/maintenance", response_model=MaintenanceRead, status_code=status.HTTP_201_CREATED
)
async def create_maintenance(
    payload: MaintenanceCreate,
    db: AsyncSession = Depends(get_db),
    _operator: Operator | None = Depends(require_operator),
) -> MaintenanceWindow:
    if (
        payload.endpoint_id is not None
        and await db.get(Endpoint, payload.endpoint_id) is None
    ):
        raise HTTPException(status_code=404, detail="Endpoint not found")
    window = MaintenanceWindow(**payload.model_dump())
    db.add(window)
    await db.flush()
    await record_audit(
        db, "maintenance.created", "maintenance", window.id, window.title
    )
    await db.commit()
    await db.refresh(window)
    return window


@router.delete("/maintenance/{window_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_maintenance(
    window_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _operator: Operator | None = Depends(require_operator),
) -> None:
    result = await db.execute(
        delete(MaintenanceWindow).where(MaintenanceWindow.id == window_id)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Maintenance window not found")
    await record_audit(db, "maintenance.deleted", "maintenance", window_id)
    await db.commit()


@router.get("/endpoints/{endpoint_id}/diagnostics", response_model=DiagnosticsRead)
async def endpoint_diagnostics(
    endpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    endpoint = await db.get(Endpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    try:
        return await inspect_endpoint(endpoint.url)
    except (OSError, TimeoutError, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Diagnostics failed: {str(exc)[:200]}"
        ) from exc


@router.get("/notifications/status", response_model=NotificationStatus)
async def get_notification_status() -> dict[str, bool]:
    return notification_status()


@router.get("/audit", response_model=list[AuditLogRead])
async def list_audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLog]:
    return list(
        (
            await db.scalars(
                select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
            )
        ).all()
    )


@router.get("/public/status")
async def public_status(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    summary = await dashboard_summary(db)
    endpoints = await list_endpoints(db)
    state = (
        "major_outage"
        if summary.down
        else "degraded"
        if summary.blocked
        else "operational"
    )
    return {
        "name": "PulseWatch Status",
        "state": state,
        "updated_at": datetime.now(UTC),
        "services": [
            {
                "name": endpoint.name,
                "status": (
                    "paused"
                    if not endpoint.is_active
                    else endpoint.latest_check.availability
                    if endpoint.latest_check
                    else "pending"
                ),
                "checked_at": endpoint.latest_check.checked_at
                if endpoint.latest_check
                else None,
            }
            for endpoint in endpoints
        ],
    }


@router.get("/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary(db: AsyncSession = Depends(get_db)) -> DashboardSummary:
    endpoints = (await db.scalars(select(Endpoint))).all()
    up = down = blocked = paused = 0
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
        elif latest and latest.status_code in {403, 429}:
            blocked += 1
        else:
            down += 1
    return DashboardSummary(
        total=len(endpoints),
        up=up,
        down=down,
        blocked=blocked,
        paused=paused,
        average_latency_ms=round(sum(latencies) / len(latencies), 2)
        if latencies
        else None,
    )
