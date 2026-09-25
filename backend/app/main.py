import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy import text

from app.api.routes import router
from app.core.config import settings
from app.core.database import SessionLocal, create_schema
from app.services.auth import bootstrap_operator


@asynccontextmanager
async def lifespan(_: FastAPI):
    await create_schema()
    await bootstrap_operator()
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness() -> dict[str, str]:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        await redis.ping()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="A required dependency is unavailable"
        ) from exc
    finally:
        await redis.aclose()
    return {"status": "ready", "database": "ok", "redis": "ok"}


@app.get("/metrics", response_class=Response)
async def prometheus_metrics() -> Response:
    async with SessionLocal() as db:
        endpoints = len((await db.scalars(text("SELECT id FROM endpoints"))).all())
        open_incidents = len(
            (
                await db.scalars(
                    text("SELECT id FROM incidents WHERE resolved_at IS NULL")
                )
            ).all()
        )
        checks = len((await db.scalars(text("SELECT id FROM check_results"))).all())
    body = (
        "# HELP pulsewatch_monitors_total Configured monitors\n"
        "# TYPE pulsewatch_monitors_total gauge\n"
        f"pulsewatch_monitors_total {endpoints}\n"
        "# HELP pulsewatch_incidents_open Active incidents\n"
        "# TYPE pulsewatch_incidents_open gauge\n"
        f"pulsewatch_incidents_open {open_incidents}\n"
        "# HELP pulsewatch_checks_total Persisted probe checks\n"
        "# TYPE pulsewatch_checks_total counter\n"
        f"pulsewatch_checks_total {checks}\n"
    )
    return Response(content=body, media_type="text/plain; version=0.0.4")


@app.websocket("/ws/checks")
async def check_events(websocket: WebSocket) -> None:
    await websocket.accept()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe("pulsewatch:checks")
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_json(json.loads(message["data"]))
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe("pulsewatch:checks")
        await pubsub.aclose()
        await redis.aclose()
