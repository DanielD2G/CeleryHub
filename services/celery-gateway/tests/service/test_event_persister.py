from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from celery_gateway.db.models import CeleryEvent
from celery_gateway.services.event_collector import EVENTS_STREAM_KEY
from celery_gateway.services.event_persister import (
    _consume_once,
    _ensure_group,
)


async def _seed(fake_redis, event: dict) -> None:
    await fake_redis.xadd(EVENTS_STREAM_KEY, {"data": json.dumps(event)})


@pytest.mark.asyncio
async def test_persister_inserts_event(fake_redis, db_session):
    await _ensure_group(fake_redis)
    await _seed(
        fake_redis,
        {"uuid": "t1", "type": "task-succeeded", "timestamp": 1700000000.0,
         "name": "tasks.add"},
    )
    processed = await _consume_once(fake_redis)
    assert processed == 1

    count = await db_session.scalar(select(func.count()).select_from(CeleryEvent))
    assert count == 1


@pytest.mark.asyncio
async def test_persister_dedups_on_retry(fake_redis, db_session):
    await _ensure_group(fake_redis)
    evt = {"uuid": "t2", "type": "task-failed", "timestamp": 1700000000.0,
           "name": "tasks.boom"}
    await _seed(fake_redis, evt)
    await _seed(fake_redis, evt)  # same uid twice
    await _consume_once(fake_redis)

    count = await db_session.scalar(select(func.count()).select_from(CeleryEvent))
    assert count == 1


@pytest.mark.asyncio
async def test_flush_batch_does_not_recreate_cached_partitions(fake_redis, db_session, monkeypatch):
    import time
    from celery_gateway.services import event_persister as ep

    ep._ensured_partitions.clear()
    calls: list = []
    real_create = ep.create_partition

    async def _spy(session, day):
        calls.append(day)
        await real_create(session, day)

    monkeypatch.setattr(ep, "create_partition", _spy)

    ts = time.time()
    await ep._flush_batch([("1-0", {"uuid": "c1", "type": "task-succeeded", "timestamp": ts, "name": "tasks.x"})])
    first_count = len(calls)
    assert first_count > 0  # partitions created on first flush

    await ep._flush_batch([("2-0", {"uuid": "c2", "type": "task-succeeded", "timestamp": ts, "name": "tasks.x"})])
    assert len(calls) == first_count  # no new partition creation: same day already cached
