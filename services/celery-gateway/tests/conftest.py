from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from celery_gateway.db.models import Base
from celery_gateway.services.cache import CeleryCache
from celery_gateway.services.inspect_cache import InspectCache
from tests._db import test_database_url


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    from sqlalchemy import text
    from celery_gateway.db.events_ddl import (
        CELERY_EVENTS_STATEMENTS,
        DROP_CELERY_EVENTS,
    )

    engine = create_async_engine(test_database_url(), echo=False)
    _regular = [t for t in Base.metadata.sorted_tables if t.name != "celery_events"]
    async with engine.begin() as conn:
        await conn.execute(text(DROP_CELERY_EVENTS))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_regular))
        for statement in CELERY_EVENTS_STATEMENTS:
            await conn.execute(text(statement))
    yield engine
    async with engine.begin() as conn:
        await conn.execute(text(DROP_CELERY_EVENTS))
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(
    db_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    @asynccontextmanager
    async def _override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    with (
        patch("celery_gateway.db.get_session", _override_get_session),
        patch("celery_gateway.routers.workflows.get_session", _override_get_session),
        patch("celery_gateway.services.scheduler.get_session", _override_get_session),
        patch("celery_gateway.services.workflow_engine.get_session", _override_get_session),
        patch("celery_gateway.services.event_collector.get_session", _override_get_session),
        patch("celery_gateway.services.event_persister.get_session", _override_get_session),
        patch("celery_gateway.services.retention.get_session", _override_get_session),
        patch("celery_gateway.services.settings_store.get_session", _override_get_session),
    ):
        async with factory() as session:
            yield session


# ---------------------------------------------------------------------------
# Redis fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def fake_redis() -> AsyncGenerator[Any, None]:
    import fakeredis.aioredis

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("celery_gateway.services.redis_client.get_redis", return_value=redis),
        patch("celery_gateway.services.celery_redis.get_redis", return_value=redis),
        patch("celery_gateway.services.event_collector.get_redis", return_value=redis),
    ):
        yield redis
    await redis.aclose()


# ---------------------------------------------------------------------------
# Celery app mock
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_celery_app() -> MagicMock:
    app = MagicMock()

    inspector = MagicMock()
    inspector.ping.return_value = {"worker1@host": {"ok": "pong"}}
    inspector.active.return_value = {}
    inspector.registered.return_value = {}
    inspector.reserved.return_value = {}
    inspector.scheduled.return_value = {}
    inspector.stats.return_value = {}
    inspector.conf.return_value = {}
    inspector.active_queues.return_value = {}

    app.control.inspect.return_value = inspector
    app.control.revoke = MagicMock()
    app.send_task = MagicMock()

    return app


# ---------------------------------------------------------------------------
# Cache mocks
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_celery_cache() -> AsyncMock:
    cache = AsyncMock(spec=CeleryCache)

    async def _get(key: str) -> Any:
        defaults: dict[str, Any] = {
            "active-tasks": [],
            "queue-depths": {"celery": 0},
            "task-history": [],
            "worker-inspect": None,
            "registered-tasks": {"byWorker": {}, "tasks": []},
            "queue-details": {
                "queueNames": ["celery"],
                "depths": {"celery": 0},
                "pending": {"celery": []},
            },
        }
        return defaults.get(key, None)

    cache.get = AsyncMock(side_effect=_get)
    return cache


@pytest.fixture
def mock_inspect_cache() -> AsyncMock:
    cache = AsyncMock(spec=InspectCache)
    cache.get = AsyncMock(return_value={})
    return cache


# ---------------------------------------------------------------------------
# HTTP client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(
    db_session: AsyncSession,
    mock_celery_cache: AsyncMock,
    mock_inspect_cache: AsyncMock,
    mock_celery_app: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    from celery_gateway.main import app

    app.state.celery_cache = mock_celery_cache
    app.state.inspect_cache = mock_inspect_cache

    with (
        patch("celery_gateway.main.celery_app", mock_celery_app),
        patch("celery_gateway.routers.tasks.celery_app", mock_celery_app),
        patch("celery_gateway.routers.control.celery_app", mock_celery_app),
        patch("celery_gateway.services.scheduler.celery_app", mock_celery_app),
    ):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as ac:
            yield ac
