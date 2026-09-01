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

from . import VERSION
from .celery_app import app as celery_app
from .config import settings
from .db import close_db, get_engine, get_session, init_db
from .routers import alerts as alerts_router
from .routers import control, event_log, events, queues, tasks, workflows, workers
from .services.cache import CeleryCache
from .services.event_collector import (
    EVENTS_STREAM_KEY,
    start_event_collector,
    stop_event_collector,
)
from .services.event_persister import start_event_persister, stop_event_persister
from .services import leadership
from .services.event_persister import EVENTS_GROUP
from .services.alerts import start_alerts, stop_alerts
from .services.exception_rollup import (
    start_exception_rollup,
    stop_exception_rollup,
)
from .services.retention import start_retention, stop_retention
from .services.scheduler import start_scheduler, stop_scheduler
from .services.inspect_cache import InspectCache
from .services.redis_client import close_redis, get_redis

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

    # beat/persister/retention are singletons: exactly one replica may run
    # them. The leader lock (Postgres advisory lock) guarantees that; with a
    # single instance it is acquired immediately.
    singleton_tasks: dict[str, Any] = {}

    async def _start_singletons() -> None:
        from .services.workflow_engine import resume_running_workflows

        try:
            await resume_running_workflows()
        except Exception:
            logger.exception("Failed to resume in-flight workflow runs")
        singleton_tasks["scheduler"] = start_scheduler()
        singleton_tasks["persister"] = start_event_persister()
        singleton_tasks["retention"] = start_retention()
        singleton_tasks["rollup"] = start_exception_rollup()
        alerts_task = start_alerts(application)
        if alerts_task is not None:
            singleton_tasks["alerts"] = alerts_task

    leadership_task = await leadership.run_when_leader(
        get_engine(), _start_singletons
    )

    yield

    # Shutdown
    leadership_task.cancel()
    try:
        await leadership_task
    except asyncio.CancelledError:
        pass
    if "scheduler" in singleton_tasks:
        await stop_scheduler(singleton_tasks["scheduler"])
    if collector_task is not None:
        await stop_event_collector(collector_task)
    if "retention" in singleton_tasks:
        await stop_retention(singleton_tasks["retention"])
    if "rollup" in singleton_tasks:
        await stop_exception_rollup(singleton_tasks["rollup"])
    if "alerts" in singleton_tasks:
        await stop_alerts(singleton_tasks["alerts"])
    if singleton_tasks.get("persister") is not None:
        await stop_event_persister(singleton_tasks["persister"])
    await leadership.release()
    celery_cache.stop()
    await close_db()
    await close_redis()


app = FastAPI(title="CeleryHub", version=VERSION, lifespan=lifespan)

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
app.include_router(workflows.router, prefix="/api")
app.include_router(queues.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(event_log.router, prefix="/api")
app.include_router(alerts_router.router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, Any]:
    try:
        loop = asyncio.get_running_loop()
        inspector = celery_app.control.inspect(timeout=2.0)
        ping: dict[str, Any] | None = await loop.run_in_executor(
            None, inspector.ping
        )
        workers_reachable = len(ping) if ping else 0
        broker_connected = True
    except Exception:
        workers_reachable = 0
        broker_connected = False

    database_connected = False
    last_event_age_seconds: float | None = None
    try:
        from sqlalchemy import text as _text

        async with get_session() as session:
            await session.execute(_text("SELECT 1"))
            database_connected = True
            age = await session.scalar(
                _text(
                    "SELECT EXTRACT(EPOCH FROM (now() - max(ingested_at))) "
                    "FROM celery_events"
                )
            )
            last_event_age_seconds = float(age) if age is not None else None
    except Exception:
        pass

    persister_pending: int | None = None
    persister_lag: int | None = None
    try:
        groups = await get_redis().xinfo_groups(EVENTS_STREAM_KEY)
        for g in groups:
            name = g.get("name")
            if isinstance(name, bytes):
                name = name.decode()
            if name == EVENTS_GROUP:
                persister_pending = int(g.get("pending", 0))
                lag = g.get("lag")
                persister_lag = int(lag) if lag is not None else None
                break
    except Exception:
        pass

    healthy = broker_connected and database_connected
    return {
        "status": "healthy" if healthy else "unhealthy",
        "broker_connected": broker_connected,
        "database_connected": database_connected,
        "workers_reachable": workers_reachable,
        "is_leader": leadership.is_leader(),
        "persister_pending": persister_pending,
        "persister_lag": persister_lag,
        "last_event_age_seconds": last_event_age_seconds,
        "version": VERSION,
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
    # Unknown API routes must be JSON 404s, not a 200 with index.html.
    if path.startswith("api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    if _static_dir is None:
        return JSONResponse({"detail": "No frontend available"}, status_code=404)

    # Try to serve the exact file
    file_path = _static_dir / path
    if file_path.is_file() and _static_dir in file_path.resolve().parents:
        return FileResponse(str(file_path))

    # SPA fallback
    index = _static_dir / "index.html"
    if index.is_file():
        return FileResponse(str(index))

    return JSONResponse({"detail": "Not found"}, status_code=404)
