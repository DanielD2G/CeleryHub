from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .celery_app import app as celery_app
from .config import settings
from .db import close_db, init_db
from .routers import beats, control, events, queues, tasks, workers
from .services.cache import CeleryCache
from .services.event_collector import start_event_collector, stop_event_collector
from .services.beat_scheduler import start_scheduler, stop_scheduler
from .services.inspect_cache import InspectCache
from .services.redis_client import close_redis

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    await init_db()

    inspect_cache = InspectCache(
        celery_app,
        timeout=settings.inspect_timeout,
        ttl=settings.inspect_cache_ttl,
    )
    application.state.inspect_cache = inspect_cache

    celery_cache = CeleryCache(inspect_cache)
    application.state.celery_cache = celery_cache

    collector_task = start_event_collector()
    scheduler_task = start_scheduler()

    yield

    # Shutdown
    stop_scheduler(scheduler_task)
    if collector_task is not None:
        await stop_event_collector(collector_task)
    celery_cache.stop()
    await close_db()
    await close_redis()


app = FastAPI(title="CeleryHub", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routers under /api
app.include_router(tasks.router, prefix="/api")
app.include_router(workers.router, prefix="/api")
app.include_router(control.router, prefix="/api")
app.include_router(beats.router, prefix="/api")
app.include_router(queues.router, prefix="/api")
app.include_router(events.router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, Any]:
    try:
        inspector = celery_app.control.inspect(timeout=2.0)
        ping = inspector.ping()
        workers_reachable = len(ping) if ping else 0
        broker_connected = True
    except Exception:
        workers_reachable = 0
        broker_connected = False

    return {
        "status": "healthy" if broker_connected else "unhealthy",
        "broker_connected": broker_connected,
        "workers_reachable": workers_reachable,
        "version": "0.1.0",
    }


# ---------------------------------------------------------------------------
# Static files / SPA catch-all
# ---------------------------------------------------------------------------


def _resolve_static_dir() -> Path | None:
    if settings.static_dir:
        p = Path(settings.static_dir).resolve()
        if p.is_dir():
            return p

    candidates = [
        Path("packages/web/dist"),
        Path("/app/packages/web/dist"),
        Path("/app/dist"),
    ]
    for p in candidates:
        if p.is_dir():
            return p.resolve()
    return None


_static_dir = _resolve_static_dir()

# Mount /assets BEFORE the catch-all so it takes priority
if _static_dir is not None:
    _assets_dir = _static_dir / "assets"
    if _assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(_assets_dir)),
            name="static-assets",
        )
    logger.info("Serving static files from %s", _static_dir)
else:
    logger.info("No static directory found — SPA will not be served")


@app.get("/{path:path}", response_model=None)
async def spa_catch_all(request: Request, path: str) -> FileResponse | JSONResponse:
    if _static_dir is None:
        return JSONResponse({"error": "No frontend available"}, status_code=404)

    # Try to serve the exact file
    file_path = _static_dir / path
    if file_path.is_file() and _static_dir in file_path.resolve().parents:
        return FileResponse(str(file_path))

    # SPA fallback
    index = _static_dir / "index.html"
    if index.is_file():
        return FileResponse(str(index))

    return JSONResponse({"error": "Not found"}, status_code=404)
