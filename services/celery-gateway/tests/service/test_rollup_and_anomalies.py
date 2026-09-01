from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from celery_gateway.services.anomalies import detect_anomalies
from celery_gateway.services.exception_rollup import rollup_once
from celery_gateway.services.partitions import ensure_partitions

pytestmark = pytest.mark.asyncio


async def _insert_event(
    session, uid: str, task_name: str, event_type: str, *,
    runtime: float | None = None, exception: str | None = None,
    hours_ago: float = 0.0,
) -> None:
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    await ensure_partitions(session, ts.date())
    await ensure_partitions(session, datetime.now(timezone.utc).date())
    await session.execute(
        text(
            "INSERT INTO celery_events "
            "(event_uid, event_time, event_type, task_id, task_name, runtime, "
            " exception, payload, ingested_at) "
            "VALUES (:uid, :ts, :etype, :uid, :tname, :rt, :exc, '{}'::jsonb, now())"
        ),
        {"uid": uid, "ts": ts, "etype": event_type, "tname": task_name,
         "rt": runtime, "exc": exception},
    )
    await session.commit()


class TestExceptionRollup:
    async def test_rollup_aggregates_by_day_and_signature(self, db_session):
        for i in range(3):
            await _insert_event(
                db_session, f"r{i}", "tasks.boom", "task-failed",
                exception="ValueError: x\ntrace", hours_ago=1,
            )
        await _insert_event(
            db_session, "r9", "tasks.boom", "task-failed",
            exception="KeyError: 'y'", hours_ago=1,
        )
        await rollup_once()

        rows = (await db_session.execute(
            text("SELECT signature, count FROM exception_rollup ORDER BY count DESC")
        )).all()
        assert rows == [("ValueError: x", 3), ("KeyError: 'y'", 1)]

    async def test_rollup_is_idempotent(self, db_session):
        await _insert_event(
            db_session, "ri1", "tasks.idem", "task-failed",
            exception="E: once", hours_ago=1,
        )
        await rollup_once()
        await rollup_once()
        count = await db_session.scalar(
            text("SELECT count FROM exception_rollup WHERE signature = 'E: once'")
        )
        assert count == 1


class TestAnomalies:
    async def test_slow_run_detected_against_own_p95(self, db_session):
        # 10 normal runs ~1s, then one at 10s (>3x p95)
        for i in range(10):
            await _insert_event(
                db_session, f"n{i}", "tasks.slow", "task-succeeded",
                runtime=1.0 + i * 0.01, hours_ago=30,
            )
        await _insert_event(
            db_session, "outlier", "tasks.slow", "task-succeeded",
            runtime=10.0, hours_ago=1,
        )
        anomalies = await detect_anomalies()
        slow = [a for a in anomalies if a["kind"] == "slow_run"]
        assert len(slow) == 1
        assert slow[0]["task_name"] == "tasks.slow"
        assert "p95" in slow[0]["detail"]

    async def test_failure_streak_detected(self, db_session):
        # History of successes, then 5 straight failures
        for i in range(20):
            await _insert_event(
                db_session, f"h{i}", "tasks.flaky", "task-succeeded",
                runtime=1.0, hours_ago=100 - i,
            )
        for i in range(5):
            await _insert_event(
                db_session, f"f{i}", "tasks.flaky", "task-failed",
                exception="E", hours_ago=5 - i,
            )
        anomalies = await detect_anomalies()
        streaks = [a for a in anomalies if a["kind"] == "failure_streak"]
        assert len(streaks) == 1
        assert streaks[0]["task_name"] == "tasks.flaky"

    async def test_no_anomalies_on_healthy_history(self, db_session):
        for i in range(10):
            await _insert_event(
                db_session, f"ok{i}", "tasks.fine", "task-succeeded",
                runtime=1.0, hours_ago=float(i),
            )
        assert await detect_anomalies() == []
