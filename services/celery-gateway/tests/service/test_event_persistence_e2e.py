from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from celery_gateway.db.models import CeleryEvent
from celery_gateway.services.event_collector import EVENTS_STREAM_KEY, _publish_to_stream
from celery_gateway.services.event_persister import _consume_once, _ensure_group


@pytest.mark.asyncio
async def test_events_buffered_then_persisted(fake_redis, db_session):
    await _ensure_group(fake_redis)

    # "Outage": events queued but not yet consumed.
    for i in range(5):
        await _publish_to_stream(
            {"uuid": f"e{i}", "type": "task-succeeded", "timestamp": 1700000000.0 + i,
             "name": "tasks.work"}
        )
    assert await fake_redis.xlen(EVENTS_STREAM_KEY) == 5

    # "Recovery": persister drains the backlog.
    processed = await _consume_once(fake_redis)
    assert processed == 5

    count = await db_session.scalar(select(func.count()).select_from(CeleryEvent))
    assert count == 5
