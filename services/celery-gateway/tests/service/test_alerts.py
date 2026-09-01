from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from celery_gateway.db.models import AlertChannel, AlertEvent, Workflow, WorkflowRun
from celery_gateway.services import alerts


@pytest.fixture(autouse=True)
def _patch_alert_sessions(db_session, monkeypatch):
    # alerts module imports get_session from ..db at module level
    from celery_gateway import db as db_module

    monkeypatch.setattr(alerts, "get_session", db_module.get_session)


async def _mk_channel(session, *, rules: dict, kind: str = "webhook") -> AlertChannel:
    ch = AlertChannel(
        id=str(uuid.uuid4()),
        name="test",
        kind=kind,
        config=json.dumps({"url": "http://example.invalid/hook"}),
        enabled=True,
        rules=json.dumps(rules),
        created_at=datetime.now(timezone.utc),
    )
    session.add(ch)
    await session.commit()
    return ch


@pytest.mark.asyncio
async def test_fire_delivers_to_subscribed_channel(db_session):
    await _mk_channel(db_session, rules={"workflow_failed": {"enabled": True}})
    with patch.object(alerts, "_deliver", new=AsyncMock(return_value=(True, None))) as d:
        sent = await alerts.fire("workflow_failed", "wf-1", "boom")
    assert sent == 1
    d.assert_awaited_once()
    events = (await db_session.execute(select(AlertEvent))).scalars().all()
    assert len(events) == 1 and events[0].delivered is True


@pytest.mark.asyncio
async def test_fire_skips_channel_without_rule(db_session):
    await _mk_channel(db_session, rules={"persister_lag": {"enabled": True}})
    with patch.object(alerts, "_deliver", new=AsyncMock(return_value=(True, None))):
        sent = await alerts.fire("workflow_failed", "wf-1", "boom")
    assert sent == 0


@pytest.mark.asyncio
async def test_cooldown_suppresses_repeat(db_session):
    await _mk_channel(db_session, rules={"workflow_failed": {"enabled": True}})
    with patch.object(alerts, "_deliver", new=AsyncMock(return_value=(True, None))):
        assert await alerts.fire("workflow_failed", "wf-1", "boom") == 1
        assert await alerts.fire("workflow_failed", "wf-1", "boom again") == 0
        # Different subject is not suppressed
        assert await alerts.fire("workflow_failed", "wf-2", "other") == 1


@pytest.mark.asyncio
async def test_delivery_failure_recorded(db_session):
    await _mk_channel(db_session, rules={"workflow_failed": {"enabled": True}})
    with patch.object(
        alerts, "_deliver", new=AsyncMock(return_value=(False, "HTTP 500"))
    ):
        sent = await alerts.fire("workflow_failed", "wf-1", "boom")
    assert sent == 0
    ev = (await db_session.execute(select(AlertEvent))).scalars().one()
    assert ev.delivered is False and ev.error == "HTTP 500"


@pytest.mark.asyncio
async def test_dead_mans_switch_fires_when_no_recent_success(db_session):
    wf = Workflow(
        id=str(uuid.uuid4()), name="dms-wf", schedule_type="cron",
        cron_expression="0 * * * *", enabled=True,
        expect_success_within_seconds=3600,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(wf)
    # Last success 2 hours ago — outside the 1h window.
    db_session.add(WorkflowRun(
        id=str(uuid.uuid4()), workflow_id=wf.id, status="succeeded",
        trigger="scheduled",
        started_at=datetime.now(timezone.utc) - timedelta(hours=2, minutes=1),
        finished_at=datetime.now(timezone.utc) - timedelta(hours=2),
    ))
    await db_session.commit()

    with patch.object(alerts, "fire", new=AsyncMock(return_value=1)) as f:
        await alerts._check_dead_mans_switches()
    f.assert_awaited_once()
    assert f.await_args.args[0] == alerts.RULE_DEAD_MANS_SWITCH
    assert f.await_args.args[1] == wf.id


@pytest.mark.asyncio
async def test_dead_mans_switch_quiet_when_recent_success(db_session):
    wf = Workflow(
        id=str(uuid.uuid4()), name="dms-ok", schedule_type="cron",
        cron_expression="0 * * * *", enabled=True,
        expect_success_within_seconds=7200,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(wf)
    db_session.add(WorkflowRun(
        id=str(uuid.uuid4()), workflow_id=wf.id, status="succeeded",
        trigger="scheduled",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        finished_at=datetime.now(timezone.utc) - timedelta(minutes=29),
    ))
    await db_session.commit()

    with patch.object(alerts, "fire", new=AsyncMock(return_value=1)) as f:
        await alerts._check_dead_mans_switches()
    f.assert_not_awaited()


@pytest.mark.asyncio
async def test_dead_mans_switch_ignores_disabled_and_unset(db_session):
    now = datetime.now(timezone.utc)
    db_session.add(Workflow(
        id=str(uuid.uuid4()), name="no-window", schedule_type="cron",
        cron_expression="0 * * * *", enabled=True,
        created_at=now, updated_at=now,
    ))
    db_session.add(Workflow(
        id=str(uuid.uuid4()), name="disabled", schedule_type="cron",
        cron_expression="0 * * * *", enabled=False,
        expect_success_within_seconds=60,
        created_at=now, updated_at=now,
    ))
    await db_session.commit()
    with patch.object(alerts, "fire", new=AsyncMock(return_value=1)) as f:
        await alerts._check_dead_mans_switches()
    f.assert_not_awaited()
