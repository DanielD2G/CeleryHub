from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select, text

from ..db import get_session
from ..db.models import CeleryEvent
from ..middleware.auth import require_auth
from ..models.event_log import (
    EventLogItem,
    EventLogPage,
    ExceptionGroupItem,
    ExceptionGroupsResponse,
    RetentionInput,
    RetentionResponse,
    TaskStatsItem,
    TaskStatsResponse,
)
from ..services.settings_store import get_retention_days, set_retention_days

router = APIRouter(tags=["event-log"], dependencies=[Depends(require_auth)])


@router.get("/event-log", response_model=EventLogPage)
async def event_log(
    task_id: str | None = Query(default=None, alias="taskId"),
    task_name: str | None = Query(default=None, alias="taskName"),
    event_type: str | None = Query(default=None, alias="eventType"),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    before: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> EventLogPage:
    stmt = select(CeleryEvent)
    if task_id:
        stmt = stmt.where(CeleryEvent.task_id == task_id)
    if task_name:
        stmt = stmt.where(CeleryEvent.task_name == task_name)
    if event_type:
        stmt = stmt.where(CeleryEvent.event_type == event_type)
    if since:
        stmt = stmt.where(CeleryEvent.event_time >= since)
    if until:
        stmt = stmt.where(CeleryEvent.event_time <= until)
    if before:
        stmt = stmt.where(CeleryEvent.event_time < before)
    stmt = stmt.order_by(desc(CeleryEvent.event_time)).limit(limit + 1)

    async with get_session() as session:
        rows = list((await session.execute(stmt)).scalars().all())

    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [EventLogItem.model_validate(r) for r in rows]
    next_cursor = rows[-1].event_time if has_more and rows else None
    return EventLogPage(items=items, next_cursor=next_cursor)


@router.get("/settings/retention", response_model=RetentionResponse)
async def get_retention() -> RetentionResponse:
    return RetentionResponse(retention_days=await get_retention_days())


@router.put("/settings/retention", response_model=RetentionResponse)
async def put_retention(body: RetentionInput) -> RetentionResponse:
    try:
        await set_retention_days(body.retention_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RetentionResponse(retention_days=await get_retention_days())


def _window(
    since: datetime | None, until: datetime | None, default_days: int
) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    return (since or now - timedelta(days=default_days), until or now)


@router.get("/event-log/stats", response_model=TaskStatsResponse)
async def event_log_stats(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
) -> TaskStatsResponse:
    """Per-task aggregates over the window (default: last 7 days).

    Success/failure counts come straight from event types; runtime
    percentiles come from task-succeeded rows, which carry runtime.
    """
    since_dt, until_dt = _window(since, until, default_days=7)
    stmt = text(
        """
        SELECT
            task_name,
            count(*) FILTER (WHERE event_type = 'task-received')  AS received,
            count(*) FILTER (WHERE event_type = 'task-succeeded') AS succeeded,
            count(*) FILTER (WHERE event_type = 'task-failed')    AS failed,
            avg(runtime)  FILTER (WHERE event_type = 'task-succeeded') AS runtime_avg,
            percentile_cont(0.5)  WITHIN GROUP (ORDER BY runtime)
                FILTER (WHERE event_type = 'task-succeeded') AS runtime_p50,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY runtime)
                FILTER (WHERE event_type = 'task-succeeded') AS runtime_p95,
            percentile_cont(0.99) WITHIN GROUP (ORDER BY runtime)
                FILTER (WHERE event_type = 'task-succeeded') AS runtime_p99
        FROM celery_events
        WHERE event_time >= :since AND event_time <= :until
          AND task_name IS NOT NULL
        GROUP BY task_name
        ORDER BY (count(*) FILTER (WHERE event_type = 'task-failed')) DESC,
                 task_name
        """
    )
    async with get_session() as session:
        rows = (
            await session.execute(stmt, {"since": since_dt, "until": until_dt})
        ).mappings().all()

    items = []
    for r in rows:
        terminal = (r["succeeded"] or 0) + (r["failed"] or 0)
        items.append(
            TaskStatsItem(
                task_name=r["task_name"],
                received=r["received"] or 0,
                succeeded=r["succeeded"] or 0,
                failed=r["failed"] or 0,
                failure_rate=(r["failed"] or 0) / terminal if terminal else 0.0,
                runtime_avg=r["runtime_avg"],
                runtime_p50=r["runtime_p50"],
                runtime_p95=r["runtime_p95"],
                runtime_p99=r["runtime_p99"],
            )
        )
    return TaskStatsResponse(since=since_dt, until=until_dt, items=items)


@router.get("/event-log/exceptions", response_model=ExceptionGroupsResponse)
async def event_log_exceptions(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> ExceptionGroupsResponse:
    """Failures grouped by task and exception signature (first line)."""
    since_dt, until_dt = _window(since, until, default_days=7)
    stmt = text(
        """
        SELECT
            task_name,
            split_part(exception, E'\n', 1) AS signature,
            count(*)        AS cnt,
            min(event_time) AS first_seen,
            max(event_time) AS last_seen,
            (array_agg(task_id ORDER BY event_time DESC))[1] AS sample_task_id
        FROM celery_events
        WHERE event_type = 'task-failed'
          AND exception IS NOT NULL
          AND event_time >= :since AND event_time <= :until
        GROUP BY task_name, split_part(exception, E'\n', 1)
        ORDER BY cnt DESC, last_seen DESC
        LIMIT :limit
        """
    )
    async with get_session() as session:
        rows = (
            await session.execute(
                stmt, {"since": since_dt, "until": until_dt, "limit": limit}
            )
        ).mappings().all()

    items = [
        ExceptionGroupItem(
            task_name=r["task_name"],
            exception=r["signature"],
            count=r["cnt"],
            first_seen=r["first_seen"],
            last_seen=r["last_seen"],
            sample_task_id=r["sample_task_id"],
        )
        for r in rows
    ]
    return ExceptionGroupsResponse(since=since_dt, until=until_dt, items=items)


@router.get("/event-log/stats/daily")
async def event_log_stats_daily(
    task_name: str = Query(alias="taskName"),
    days: int = Query(default=30, ge=1, le=365),
) -> list[dict]:
    """Per-day series for one task: counts and runtime percentiles.

    Feeds the task-detail sparkline and failure-rate chart.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = text(
        """
        SELECT
            (event_time AT TIME ZONE 'UTC')::date AS day,
            count(*) FILTER (WHERE event_type = 'task-succeeded') AS succeeded,
            count(*) FILTER (WHERE event_type = 'task-failed')    AS failed,
            avg(runtime)  FILTER (WHERE event_type = 'task-succeeded') AS runtime_avg,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY runtime)
                FILTER (WHERE event_type = 'task-succeeded') AS runtime_p50,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY runtime)
                FILTER (WHERE event_type = 'task-succeeded') AS runtime_p95
        FROM celery_events
        WHERE task_name = :task_name AND event_time >= :since
        GROUP BY 1
        ORDER BY 1
        """
    )
    async with get_session() as session:
        rows = (
            await session.execute(stmt, {"task_name": task_name, "since": since})
        ).mappings().all()
    return [
        {
            "day": r["day"].isoformat(),
            "succeeded": r["succeeded"] or 0,
            "failed": r["failed"] or 0,
            "runtimeAvg": r["runtime_avg"],
            "runtimeP50": r["runtime_p50"],
            "runtimeP95": r["runtime_p95"],
        }
        for r in rows
    ]


@router.get("/event-log/exceptions/history")
async def exception_history(
    task_name: str | None = Query(default=None, alias="taskName"),
    days: int = Query(default=365, ge=1, le=730),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    """Long-horizon exception history from the daily rollup table, which
    outlives celery_events retention."""
    since = datetime.now(timezone.utc).date() - timedelta(days=days)
    sql = """
        SELECT task_name, signature,
               sum(count) AS total,
               min(day) AS first_day, max(day) AS last_day,
               max(last_seen) AS last_seen
        FROM exception_rollup
        WHERE day >= :since
    """
    params: dict = {"since": since, "limit": limit}
    if task_name:
        sql += " AND task_name = :task_name"
        params["task_name"] = task_name
    sql += """
        GROUP BY task_name, signature
        ORDER BY total DESC, last_seen DESC
        LIMIT :limit
    """
    async with get_session() as session:
        rows = (await session.execute(text(sql), params)).mappings().all()
    return [
        {
            "taskName": r["task_name"],
            "exception": r["signature"],
            "count": int(r["total"]),
            "firstDay": r["first_day"].isoformat(),
            "lastDay": r["last_day"].isoformat(),
            "lastSeen": r["last_seen"].isoformat() if r["last_seen"] else None,
        }
        for r in rows
    ]


@router.get("/event-log/anomalies")
async def event_log_anomalies() -> list[dict]:
    """Active anomalies: runs far above their own p95, and failure streaks."""
    from ..services.anomalies import detect_anomalies

    out = []
    for a in await detect_anomalies():
        out.append(
            {
                "kind": a["kind"],
                "taskName": a["task_name"],
                "taskId": a["task_id"],
                "detectedAt": a["detected_at"].isoformat()
                if a["detected_at"]
                else None,
                "detail": a["detail"],
            }
        )
    return out
