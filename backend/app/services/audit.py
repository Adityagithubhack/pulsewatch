import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def record_audit(
    db: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | str | None = None,
    detail: str | None = None,
    actor: str = "operator",
) -> None:
    db.add(
        AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            actor=actor,
            detail=detail,
        )
    )
