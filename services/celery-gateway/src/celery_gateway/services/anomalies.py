from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from ..config import settings
from ..db import get_session

# Thresholds relative to each task's own history — no ML, just "3x its p95"
# and "failing repeatedly against a low historical failure rate".
RUNTIME_FACTOR = settings.celeryhub_anomaly_runtime_factor
CONSECUTIVE_FAILURES = settings.celeryhub_anomaly_consecutive_failures
HISTORY_DAYS = 30
RECENT_HOURS = 24

_SLOW_RUNS = text(
    """
    WITH history AS (
        SELECT task_name,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY runtime) AS p95,
               count(*) AS n
        FROM celery_events
        WHERE event_type = 'task-succeeded'
          AND runtime IS NOT NULL AND task_name IS NOT NULL
          AND event_time >= :history_since
          -- Baseline is the history BEFORE the recent window, so an outlier
          -- can't inflate its own p95 out of detection.
          AND event_time < :recent_since
        GROUP BY task_name
        HAVING count(*) >= 5
    )
    SELECT e.task_name, e.task_id, e.event_time, e.runtime, h.p95
    FROM celery_events e
    JOIN history h ON h.task_name = e.task_name
    WHERE e.event_type = 'task-succeeded'
      AND e.runtime IS NOT NULL
      AND e.event_time >= :recent_since
      AND e.runtime > h.p95 * :factor
    ORDER BY e.event_time DESC
    LIMIT 50
    """
)

_FAILURE_STREAKS = text(
    """
    WITH terminal AS (
        SELECT task_name, event_time, event_type,
               row_number() OVER (PARTITION BY task_name ORDER BY event_time DESC) AS rn
        FROM celery_events
        WHERE event_type IN ('task-succeeded', 'task-failed')
          AND task_name IS NOT NULL
          AND event_time >= :history_since
    ),
    streaks AS (
        SELECT task_name,
               count(*) FILTER (WHERE rn <= :streak AND event_type = 'task-failed') AS recent_failures,
               count(*) FILTER (WHERE event_type = 'task-failed')::float
                   / nullif(count(*), 0) AS historical_rate,
               max(event_time) FILTER (WHERE rn = 1) AS last_seen
        FROM terminal
        GROUP BY task_name
    )
    SELECT task_name, recent_failures, round(historical_rate::numeric, 4), last_seen
    FROM streaks
    WHERE recent_failures >= :streak
    ORDER BY last_seen DESC
    """
)


async def detect_anomalies() -> list[dict[str, Any]]:
    """Current anomalies: slow runs (last 24h) and active failure streaks."""
    now = datetime.now(timezone.utc)
    history_since = now - timedelta(days=HISTORY_DAYS)
    recent_since = now - timedelta(hours=RECENT_HOURS)

    out: list[dict[str, Any]] = []
    async with get_session() as session:
        slow = (
            await session.execute(
                _SLOW_RUNS,
                {
                    "history_since": history_since,
                    "recent_since": recent_since,
                    "factor": RUNTIME_FACTOR,
                },
            )
        ).all()
        for task_name, task_id, event_time, runtime, p95 in slow:
            out.append(
                {
                    "kind": "slow_run",
                    "task_name": task_name,
                    "task_id": task_id,
                    "detected_at": event_time,
                    "detail": (
                        f"runtime {runtime:.1f}s is {runtime / p95:.1f}x its "
                        f"30-day p95 ({p95:.1f}s)"
                    ),
                }
            )

        streaks = (
            await session.execute(
                _FAILURE_STREAKS,
                {"history_since": history_since, "streak": CONSECUTIVE_FAILURES},
            )
        ).all()
        for task_name, failures, rate, last_seen in streaks:
            out.append(
                {
                    "kind": "failure_streak",
                    "task_name": task_name,
                    "task_id": None,
                    "detected_at": last_seen,
                    "detail": (
                        f"last {failures} terminal events are all failures "
                        f"(historical failure rate {float(rate or 0) * 100:.1f}%)"
                    ),
                }
            )
    return out


async def check_and_alert() -> None:
    """Feed anomalies into the alert pipeline (rule: anomaly)."""
    from .alerts import RULE_ANOMALY, fire

    for a in await detect_anomalies():
        subject = f"{a['kind']}:{a['task_name']}"
        await fire(RULE_ANOMALY, subject, f"{a['task_name']}: {a['detail']}")
