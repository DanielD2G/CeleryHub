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


@pytest.mark.asyncio
async def test_failed_event_resolves_name_from_task_runs(fake_redis, db_session):
    """The hot-layer meta hash gets a name for terminal events that never had
    a task-received — so the UI stops showing 'unknown'."""
    import uuid as _uuid
    from datetime import datetime, timezone

    from celery_gateway.db.models import StepRun, TaskRun, Workflow, WorkflowRun
    from celery_gateway.services.event_collector import _persist_event

    now = datetime.now(timezone.utc)
    wf_id = str(_uuid.uuid4())
    db_session.add(Workflow(
        id=wf_id, name="col-wf", schedule_type="none", enabled=True,
        total_run_count=0, created_at=now, updated_at=now,
    ))
    db_session.add(WorkflowRun(
        id="col-run", workflow_id=wf_id, status="running",
        trigger="manual", started_at=now,
    ))
    db_session.add(StepRun(
        id="col-sr", workflow_run_id="col-run", step_id="s",
        step_label="S", status="running", started_at=now,
    ))
    db_session.add(TaskRun(
        id="col-tr", step_run_id="col-sr", task_id="colfail-1",
        task_name="scrape_slot_one", status="SENT",
    ))
    await db_session.commit()

    await _persist_event({
        "uuid": "colfail-1", "type": "task-failed",
        "timestamp": 1700000070.0, "hostname": "celery@w1",
        "exception": "NotRegistered('scrape_slot_one')",
    })

    meta = await fake_redis.hgetall("celeryhub:tasks:colfail-1")
    decoded = {
        (k.decode() if isinstance(k, bytes) else k):
        (v.decode() if isinstance(v, bytes) else v)
        for k, v in meta.items()
    }
    assert decoded.get("name") == "scrape_slot_one"
    assert decoded.get("status") == "FAILURE"
    assert "NotRegistered" in decoded.get("exception", "")
