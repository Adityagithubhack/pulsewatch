import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CheckStatus(str, enum.Enum):
    up = "up"
    down = "down"


class Endpoint(Base):
    __tablename__ = "endpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(2048))
    method: Mapped[str] = mapped_column(String(8), default="GET")
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10)
    expected_status: Mapped[int] = mapped_column(Integer, default=200)
    failure_threshold: Mapped[int] = mapped_column(
        Integer, default=2, server_default="2"
    )
    recovery_threshold: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1"
    )
    ssl_expiry_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    checks: Mapped[list["CheckResult"]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )
    incidents: Mapped[list["Incident"]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )


class CheckResult(Base):
    __tablename__ = "check_results"
    __table_args__ = (Index("ix_check_endpoint_time", "endpoint_id", "checked_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("endpoints.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[CheckStatus] = mapped_column(Enum(CheckStatus, name="check_status"))
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str] = mapped_column(
        String(80), default="local", server_default="local"
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    endpoint: Mapped[Endpoint] = relationship(back_populates="checks")


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incident_endpoint_opened", "endpoint_id", "opened_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("endpoints.id", ondelete="CASCADE"), index=True
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    opening_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(
        String(20), default="critical", server_default="critical"
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    endpoint: Mapped[Endpoint] = relationship(back_populates="incidents")


class MaintenanceWindow(Base):
    __tablename__ = "maintenance_windows"
    __table_args__ = (Index("ix_maintenance_window_time", "starts_at", "ends_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    endpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("endpoints.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(160))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(60))
    resource_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor: Mapped[str] = mapped_column(
        String(120), default="system", server_default="system"
    )
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Operator(Base):
    __tablename__ = "operators"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(
        String(30), default="owner", server_default="owner"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OperatorSession(Base):
    __tablename__ = "operator_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("operators.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
