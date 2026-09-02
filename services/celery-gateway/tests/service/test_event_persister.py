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
    await ep._flush_batch([("1-0", {"uuid": "c1", "type": "task-succeeded", "timestamp": ts, "name": "tasks.x"})], fake_redis)
    first_count = len(calls)
    assert first_count > 0  # partitions created on first flush

    await ep._flush_batch([("2-0", {"uuid": "c2", "type": "task-succeeded", "timestamp": ts, "name": "tasks.x"})], fake_redis)
    assert len(calls) == first_count  # no new partition creation: same day already cached


# ---------------------------------------------------------------------------
# task_name backfill
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_from_same_batch(fake_redis, db_session):
    """started/succeeded events lack "name"; the received event in the same
    batch supplies it."""
    from celery_gateway.services import event_persister as ep

    ep._task_names.clear()
    await _ensure_group(fake_redis)
    await _seed(fake_redis, {"uuid": "bf1", "type": "task-received",
                             "timestamp": 1700000000.0, "name": "tasks.scrape"})
    await _seed(fake_redis, {"uuid": "bf1", "type": "task-succeeded",
                             "timestamp": 1700000010.0, "runtime": 10.0})
    await _consume_once(fake_redis)

    names = (await db_session.execute(
        select(CeleryEvent.event_type, CeleryEvent.task_name)
    )).all()
    assert dict(names) == {
        "task-received": "tasks.scrape",
        "task-succeeded": "tasks.scrape",
    }


@pytest.mark.asyncio
async def test_backfill_from_cache_across_batches(fake_redis, db_session):
    from celery_gateway.services import event_persister as ep

    ep._task_names.clear()
    await _ensure_group(fake_redis)
    await _seed(fake_redis, {"uuid": "bf2", "type": "task-received",
                             "timestamp": 1700000000.0, "name": "tasks.later"})
    await _consume_once(fake_redis)
    # Second batch: terminal event arrives alone, name resolved from cache.
    await _seed(fake_redis, {"uuid": "bf2", "type": "task-failed",
                             "timestamp": 1700000020.0})
    await _consume_once(fake_redis)

    name = await db_session.scalar(
        select(CeleryEvent.task_name).where(
            CeleryEvent.event_type == "task-failed"
        )
    )
    assert name == "tasks.later"


@pytest.mark.asyncio
async def test_backfill_from_redis_hot_layer(fake_redis, db_session):
    """Process restarted (empty in-memory cache): the name comes from the
    collector's Redis task-metadata hash."""
    from celery_gateway.services import event_persister as ep

    ep._task_names.clear()
    await fake_redis.hset("celeryhub:tasks:bf3", mapping={"name": "tasks.hot"})
    await _ensure_group(fake_redis)
    await _seed(fake_redis, {"uuid": "bf3", "type": "task-succeeded",
                             "timestamp": 1700000030.0, "runtime": 1.5})
    await _consume_once(fake_redis)

    name = await db_session.scalar(select(CeleryEvent.task_name))
    assert name == "tasks.hot"


@pytest.mark.asyncio
async def test_backfill_leaves_null_when_unknown(fake_redis, db_session):
    from celery_gateway.services import event_persister as ep

    ep._task_names.clear()
    await _ensure_group(fake_redis)
    await _seed(fake_redis, {"uuid": "bf4", "type": "task-succeeded",
                             "timestamp": 1700000040.0})
    await _consume_once(fake_redis)

    name = await db_session.scalar(select(CeleryEvent.task_name))
    assert name is None


# ---------------------------------------------------------------------------
# XAUTOCLAIM crash recovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_stale_recovers_unacked_entries(fake_redis, db_session, monkeypatch):
    """Entries read but never acked (hard kill between XREADGROUP and XACK)
    are re-delivered by _claim_stale and end up persisted."""
    from celery_gateway.services import event_persister as ep

    monkeypatch.setattr(ep, "_CLAIM_MIN_IDLE_MS", 0)
    await _ensure_group(fake_redis)
    await _seed(fake_redis, {"uuid": "cl1", "type": "task-succeeded",
                             "timestamp": 1700000050.0, "name": "tasks.claim"})
    # Simulate the crash: read without ack.
    await fake_redis.xreadgroup(
        ep.EVENTS_GROUP, "persister-1", {EVENTS_STREAM_KEY: ">"}, count=10
    )
    count = await db_session.scalar(select(func.count()).select_from(CeleryEvent))
    assert count == 0  # nothing persisted yet
    # Close the read transaction: create_partition inside the flush needs an
    # exclusive lock on celery_events and would wait on it forever.
    await db_session.rollback()

    claimed = await ep._claim_stale(fake_redis)
    assert claimed == 1
    count = await db_session.scalar(select(func.count()).select_from(CeleryEvent))
    assert count == 1
    # PEL is drained
    pending = await fake_redis.xpending(EVENTS_STREAM_KEY, ep.EVENTS_GROUP)
    assert pending["pending"] == 0


@pytest.mark.asyncio
async def test_claim_stale_noop_when_nothing_pending(fake_redis, db_session):
    from celery_gateway.services import event_persister as ep

    await _ensure_group(fake_redis)
    assert await ep._claim_stale(fake_redis) == 0


@pytest.mark.asyncio
async def test_backfill_from_task_runs_table(fake_redis, db_session):
    """A NotRegistered task emits only task-failed with no name anywhere in
    Redis — but the engine's task_runs row has it."""
    import uuid as _uuid
    from datetime import datetime, timezone

    from celery_gateway.db.models import (
        StepRun,
        TaskRun,
        Workflow,
        WorkflowRun,
    )
    from celery_gateway.services import event_persister as ep_mod

    ep_mod._task_names.clear()
    now = datetime.now(timezone.utc)
    wf_id = str(_uuid.uuid4())
    db_session.add(Workflow(
        id=wf_id, name="bf-wf", schedule_type="none", enabled=True,
        total_run_count=0, created_at=now, updated_at=now,
    ))
    db_session.add(WorkflowRun(
        id="bf-run", workflow_id=wf_id, status="running",
        trigger="manual", started_at=now,
    ))
    db_session.add(StepRun(
        id="bf-sr", workflow_run_id="bf-run", step_id="s",
        step_label="S", status="running", started_at=now,
    ))
    db_session.add(TaskRun(
        id="bf-tr", step_run_id="bf-sr", task_id="notreg-1",
        task_name="scrape_slot_one", status="SENT",
    ))
    await db_session.commit()

    await _ensure_group(fake_redis)
    await _seed(fake_redis, {
        "uuid": "notreg-1", "type": "task-failed",
        "timestamp": 1700000060.0,
        "exception": "NotRegistered('scrape_slot_one')",
    })
    await _consume_once(fake_redis)

    name = await db_session.scalar(
        select(CeleryEvent.task_name).where(CeleryEvent.task_id == "notreg-1")
    )
    assert name == "scrape_slot_one"
