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


async def _insert_full_event(
    session: AsyncSession,
    uid: str,
    task_name: str | None,
    event_type: str,
    runtime: float | None = None,
    exception: str | None = None,
) -> None:
    await ensure_partitions(session, datetime.now(timezone.utc).date())
    await session.execute(
        text(
            "INSERT INTO celery_events "
            "(event_uid, event_time, event_type, task_id, task_name, runtime, "
            " exception, payload, ingested_at) "
            "VALUES (:uid, now(), :etype, :uid, :tname, :rt, :exc, "
            " '{}'::jsonb, now())"
        ),
        {"uid": uid, "etype": event_type, "tname": task_name,
         "rt": runtime, "exc": exception},
    )
    await session.commit()


@pytest.mark.asyncio
async def test_stats_aggregates_per_task(client, db_session: AsyncSession):
    for i, rt in enumerate([1.0, 2.0, 3.0, 10.0]):
        await _insert_full_event(
            db_session, f"s{i}", "tasks.stats", "task-succeeded", runtime=rt
        )
    await _insert_full_event(db_session, "f1", "tasks.stats", "task-failed")
    await _insert_full_event(db_session, "r1", "tasks.stats", "task-received")

    resp = await client.get("/api/event-log/stats")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    it = items[0]
    assert it["taskName"] == "tasks.stats"
    assert it["succeeded"] == 4
    assert it["failed"] == 1
    assert it["received"] == 1
    assert it["failureRate"] == pytest.approx(0.2)
    assert it["runtimeAvg"] == pytest.approx(4.0)
    assert it["runtimeP50"] == pytest.approx(2.5)


@pytest.mark.asyncio
async def test_stats_excludes_null_task_name(client, db_session: AsyncSession):
    await _insert_full_event(db_session, "n1", None, "task-succeeded", runtime=1.0)
    resp = await client.get("/api/event-log/stats")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


@pytest.mark.asyncio
async def test_exceptions_grouped_by_signature(client, db_session: AsyncSession):
    for i in range(3):
        await _insert_full_event(
            db_session, f"e{i}", "tasks.boom", "task-failed",
            exception="ValueError: bad input\nmore detail",
        )
    await _insert_full_event(
        db_session, "e9", "tasks.boom", "task-failed",
        exception="KeyError: 'x'",
    )

    resp = await client.get("/api/event-log/exceptions")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    top = items[0]
    assert top["exception"] == "ValueError: bad input"
    assert top["count"] == 3
    assert top["taskName"] == "tasks.boom"
    assert top["sampleTaskId"] is not None


@pytest.mark.asyncio
async def test_daily_stats_series(client, db_session: AsyncSession):
    for i, rt in enumerate([1.0, 2.0]):
        await _insert_full_event(
            db_session, f"d{i}", "tasks.daily", "task-succeeded", runtime=rt
        )
    await _insert_full_event(db_session, "d9", "tasks.daily", "task-failed")

    resp = await client.get("/api/event-log/stats/daily?taskName=tasks.daily")
    assert resp.status_code == 200
    days = resp.json()
    assert len(days) == 1
    assert days[0]["succeeded"] == 2
    assert days[0]["failed"] == 1
    assert days[0]["runtimeP50"] == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_exception_history_reads_rollup(client, db_session: AsyncSession):
    from celery_gateway.services.exception_rollup import rollup_once

    await _insert_full_event(
        db_session, "eh1", "tasks.hist", "task-failed",
        exception="RuntimeError: kaput\ndetail",
    )
    await rollup_once()

    resp = await client.get("/api/event-log/exceptions/history")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["exception"] == "RuntimeError: kaput"
    assert items[0]["count"] == 1

    resp = await client.get(
        "/api/event-log/exceptions/history?taskName=tasks.other"
    )
    assert resp.json() == []


@pytest.mark.asyncio
async def test_anomalies_endpoint_shape(client, db_session: AsyncSession):
    resp = await client.get("/api/event-log/anomalies")
    assert resp.status_code == 200
    assert resp.json() == []
