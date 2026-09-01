from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from celery_gateway.services.partitions import ensure_partitions


async def _insert_event(session: AsyncSession, task_name: str, event_type: str) -> None:
    await ensure_partitions(session, datetime.now(timezone.utc).date())
    await session.execute(
        text(
            "INSERT INTO celery_events "
            "(event_uid, event_time, event_type, task_id, task_name, payload, ingested_at) "
            "VALUES (:uid, now(), :etype, :tid, :tname, '{}'::jsonb, now())"
        ),
        {
            "uid": f"{task_name}-{event_type}",
            "etype": event_type,
            "tid": task_name,
            "tname": task_name,
        },
    )
    await session.commit()


@pytest.mark.asyncio
async def test_event_log_returns_inserted_events(client, db_session: AsyncSession):
    await _insert_event(db_session, "tasks.alpha", "task-succeeded")
    resp = await client.get("/api/event-log")
    assert resp.status_code == 200
    body = resp.json()
    assert any(i["taskName"] == "tasks.alpha" for i in body["items"])


@pytest.mark.asyncio
async def test_event_log_filters_by_type(client, db_session: AsyncSession):
    await _insert_event(db_session, "tasks.beta", "task-failed")
    resp = await client.get("/api/event-log", params={"eventType": "task-failed"})
    assert resp.status_code == 200
    assert all(i["eventType"] == "task-failed" for i in resp.json()["items"])


@pytest.mark.asyncio
async def test_get_and_put_retention(client):
    put = await client.put("/api/settings/retention", json={"retentionDays": 45})
    assert put.status_code == 200
    assert put.json()["retentionDays"] == 45

    get = await client.get("/api/settings/retention")
    assert get.json()["retentionDays"] == 45


@pytest.mark.asyncio
async def test_put_retention_rejects_zero(client):
    resp = await client.put("/api/settings/retention", json={"retentionDays": 0})
    assert resp.status_code == 400
