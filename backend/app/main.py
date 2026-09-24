import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.routes import router
from app.core.config import settings
from app.core.database import create_schema


@asynccontextmanager
async def lifespan(_: FastAPI):
    await create_schema()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
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

