from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .celery_app import app as celery_app
from .config import settings
from .routers import control, tasks, workers
from .services.inspect_cache import InspectCache


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.inspect_cache = InspectCache(
        celery_app,
        timeout=settings.inspect_timeout,
        ttl=settings.inspect_cache_ttl,
    )
    yield


app = FastAPI(title="Celery Gateway", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(workers.router)
app.include_router(control.router)


@app.get("/health")
async def health():
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
