import base64
import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.models import Operator, OperatorSession


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_raw, digest_raw = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        candidate = hash_password(password, base64.urlsafe_b64decode(salt_raw)).split(
            "$", 2
        )[2]
        return hmac.compare_digest(candidate, digest_raw)
    except (ValueError, TypeError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def bootstrap_operator() -> None:
    if not settings.auth_enabled:
        return
    if not settings.admin_email or not settings.admin_password:
        raise RuntimeError("AUTH_ENABLED requires ADMIN_EMAIL and ADMIN_PASSWORD")
    async with SessionLocal() as db:
        existing = await db.scalar(
            select(Operator).where(Operator.email == settings.admin_email.lower())
        )
        if existing is None:
            db.add(
                Operator(
                    email=settings.admin_email.lower(),
                    password_hash=hash_password(settings.admin_password),
                    role="owner",
                )
            )
            await db.commit()


async def authenticate_session(
    pulsewatch_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> Operator | None:
    if not settings.auth_enabled:
        return None
    if not pulsewatch_session:
        return None
    row = await db.execute(
        select(OperatorSession, Operator)
        .join(Operator, Operator.id == OperatorSession.operator_id)
        .where(
            OperatorSession.token_hash == token_digest(pulsewatch_session),
            OperatorSession.expires_at > datetime.now(UTC),
            Operator.is_active.is_(True),
        )
    )
    pair = row.first()
    return pair[1] if pair else None


async def require_operator(
    operator: Operator | None = Depends(authenticate_session),
) -> Operator | None:
    if settings.auth_enabled and operator is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return operator


async def create_session(db: AsyncSession, operator: Operator) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(40)
    expires_at = datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours)
    db.add(
        OperatorSession(
            operator_id=operator.id,
            token_hash=token_digest(token),
            expires_at=expires_at,
        )
    )
    await db.commit()
    return token, expires_at
