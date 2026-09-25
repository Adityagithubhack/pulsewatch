import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.models import CheckStatus
from app.services.url_safety import validate_monitor_url


class EndpointCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    url: str = Field(max_length=2048)
    method: str = "GET"
    interval_seconds: int = Field(default=60, ge=30, le=86400)
    timeout_seconds: int = Field(default=10, ge=1, le=30)
    expected_status: int = Field(default=200, ge=100, le=599)
    failure_threshold: int = Field(default=2, ge=1, le=10)
    recovery_threshold: int = Field(default=1, ge=1, le=10)
    ssl_expiry_enabled: bool = True

    _validate_url = field_validator("url")(validate_monitor_url)

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        value = value.upper()
        if value not in {"GET", "HEAD"}:
            raise ValueError("Only GET and HEAD are supported")
        return value


class EndpointUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    interval_seconds: int | None = Field(default=None, ge=30, le=86400)
    timeout_seconds: int | None = Field(default=None, ge=1, le=30)
    expected_status: int | None = Field(default=None, ge=100, le=599)
    failure_threshold: int | None = Field(default=None, ge=1, le=10)
    recovery_threshold: int | None = Field(default=None, ge=1, le=10)
    ssl_expiry_enabled: bool | None = None
    is_active: bool | None = None


class CheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    endpoint_id: uuid.UUID
    status: CheckStatus
    status_code: int | None
    latency_ms: float | None
    error: str | None
    region: str = "local"
    checked_at: datetime

    @computed_field(return_type=str)
    @property
    def availability(self) -> str:
        if self.status.value == "up":
            return "up"
        if self.status_code in {403, 429}:
            return "blocked"
        return "down"


class EndpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str
    method: str
    interval_seconds: int
    timeout_seconds: int
    expected_status: int
    failure_threshold: int
    recovery_threshold: int
    ssl_expiry_enabled: bool
    is_active: bool
    created_at: datetime
    latest_check: CheckRead | None = None


class DashboardSummary(BaseModel):
    total: int
    up: int
    down: int
    blocked: int = 0
    paused: int
    average_latency_ms: float | None


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    endpoint_id: uuid.UUID
    endpoint_name: str
    endpoint_url: str
    opened_at: datetime
    resolved_at: datetime | None
    opening_status_code: int | None
    cause: str | None
    severity: str = "critical"
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    notes: str | None = None


class IncidentUpdate(BaseModel):
    acknowledged_by: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    resolve: bool = False


class MaintenanceCreate(BaseModel):
    endpoint_id: uuid.UUID | None = None
    title: str = Field(min_length=2, max_length=160)
    starts_at: datetime
    ends_at: datetime

    @field_validator("ends_at")
    @classmethod
    def validate_end(cls, value: datetime, info):
        starts_at = info.data.get("starts_at")
        if starts_at is not None and value <= starts_at:
            raise ValueError("Maintenance end must be after its start")
        return value


class MaintenanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    endpoint_id: uuid.UUID | None
    title: str
    starts_at: datetime
    ends_at: datetime
    created_at: datetime


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    resource_type: str
    resource_id: str | None
    actor: str
    detail: str | None
    created_at: datetime


class DiagnosticsRead(BaseModel):
    hostname: str
    resolved_addresses: list[str]
    dns_latency_ms: float | None
    tls_enabled: bool
    tls_issuer: str | None
    tls_expires_at: datetime | None
    tls_days_remaining: int | None
    tls_status: str


class NotificationStatus(BaseModel):
    telegram: bool
    webhook: bool
    email: bool


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)


class AuthStatus(BaseModel):
    enabled: bool
    authenticated: bool
    email: str | None = None
    role: str | None = None


class EndpointMetrics(BaseModel):
    endpoint_id: uuid.UUID
    window_hours: int
    total_checks: int
    successful_checks: int
    uptime_percentage: float | None
    average_latency_ms: float | None
    p95_latency_ms: float | None
    incident_count: int
    series: list[CheckRead]
