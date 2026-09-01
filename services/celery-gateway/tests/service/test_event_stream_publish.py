from __future__ import annotations

import pytest

from celery_gateway.services.event_collector import (
    EVENTS_STREAM_KEY,
    _publish_to_stream,
)


@pytest.mark.asyncio
async def test_publish_adds_to_stream(fake_redis):
    await _publish_to_stream(
        {"uuid": "x", "type": "task-succeeded", "timestamp": 1700000000.0}
    )
    length = await fake_redis.xlen(EVENTS_STREAM_KEY)
    assert length == 1
