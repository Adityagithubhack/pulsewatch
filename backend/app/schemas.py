import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import CheckStatus
from app.services.url_safety import validate_monitor_url


class EndpointCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    url: str = Field(max_length=2048)
    method: str = "GET"
    interval_seconds: int = Field(default=60, ge=30, le=86400)
    timeout_seconds: int = Field(default=10, ge=1, le=30)
    expected_status: int = Field(default=200, ge=100, le=599)

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
    is_active: bool | None = None


class CheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    endpoint_id: uuid.UUID
    status: CheckStatus
    status_code: int | None
    latency_ms: float | None
    error: str | None
    checked_at: datetime


class EndpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str
    method: str
    interval_seconds: int
    timeout_seconds: int
    expected_status: int
    is_active: bool
    created_at: datetime
    latest_check: CheckRead | None = None


class DashboardSummary(BaseModel):
    total: int
    up: int
    down: int
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
