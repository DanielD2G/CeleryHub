from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select

from ..db import get_session
from ..db.models import CeleryEvent
from ..middleware.auth import require_auth
from ..models.event_log import (
    EventLogItem,
    EventLogPage,
    RetentionInput,
    RetentionResponse,
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
