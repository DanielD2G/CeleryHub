from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import delete, desc, select, update

from ..db import get_session
from ..db.models import BeatRun, BeatSchedule
from ..middleware.auth import require_auth
from ..models.beats import (
    BeatRunResponse,
    BeatScheduleResponse,
    CreateBeatInput,
    UpdateBeatInput,
)
from ..services.beat_scheduler import (
    compute_next_run_at,
    dispatch_task,
    validate_cron_expression,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/beats", tags=["beats"])


@router.get("", response_model=list[BeatScheduleResponse])
async def list_beats() -> Any:
    async with get_session() as session:
        result = await session.execute(
            select(BeatSchedule).order_by(desc(BeatSchedule.created_at))
        )
        return result.scalars().all()


@router.post("", response_model=None, dependencies=[Depends(require_auth)])
async def create_beat(body: CreateBeatInput) -> JSONResponse:
    args_raw = body.args or "[]"
    kwargs_raw = body.kwargs or "{}"
    queue = body.queue or "celery"
    enabled = body.enabled if body.enabled is not None else True

    # Cross-field validation: schedule-type-specific requirements
    if body.schedule_type == "interval":
        if not body.interval_seconds or body.interval_seconds <= 0:
            raise HTTPException(
                status_code=400,
                detail="Interval seconds must be a positive number",
            )
    elif body.schedule_type == "cron":
        if not body.cron_expression:
            raise HTTPException(
                status_code=400,
                detail="Cron expression is required",
            )
        cron_error = validate_cron_expression(body.cron_expression)
        if cron_error:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cron: {cron_error}",
            )

    beat_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    next_run_at: datetime | None = None
    if enabled:
        try:
            next_run_at = compute_next_run_at(
                body.schedule_type, body.interval_seconds, body.cron_expression
            )
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to compute next run: {exc}",
            ) from exc

    async with get_session() as session:
        beat = BeatSchedule(
            id=beat_id,
            name=body.name,
            task_names=json.dumps(body.task_names),
            args=args_raw,
            kwargs=kwargs_raw,
            queue=queue,
            schedule_type=body.schedule_type,
            interval_seconds=body.interval_seconds,
            cron_expression=body.cron_expression,
            enabled=enabled,
            max_run_count=body.max_run_count,
            total_run_count=0,
            next_run_at=next_run_at,
            created_at=now,
            updated_at=now,
        )
        session.add(beat)
        await session.commit()

    return JSONResponse({"id": beat_id}, status_code=201)


@router.get("/{beat_id}", response_model=BeatScheduleResponse)
async def get_beat(beat_id: str) -> Any:
    async with get_session() as session:
        result = await session.execute(
            select(BeatSchedule).where(BeatSchedule.id == beat_id).limit(1)
        )
        beat = result.scalar_one_or_none()
        if not beat:
            raise HTTPException(status_code=404, detail="Beat not found")
        return beat


@router.put("/{beat_id}", response_model=None, dependencies=[Depends(require_auth)])
async def update_beat(beat_id: str, body: UpdateBeatInput) -> JSONResponse:
    updates = body.model_dump(exclude_unset=True)

    async with get_session() as session:
        result = await session.execute(
            select(BeatSchedule).where(BeatSchedule.id == beat_id).limit(1)
        )
        existing = result.scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="Beat not found")

        task_names = updates.get("task_names")
        if task_names is not None and len(task_names) == 0:
            raise HTTPException(
                status_code=400,
                detail="At least one task must be selected",
            )

        schedule_type = updates.get("schedule_type", existing.schedule_type)
        interval_seconds = updates.get("interval_seconds", existing.interval_seconds)
        cron_expression = updates.get("cron_expression", existing.cron_expression)

        if schedule_type == "cron" and cron_expression:
            cron_error = validate_cron_expression(cron_expression)
            if cron_error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid cron: {cron_error}",
                )

        enabled = updates.get("enabled", existing.enabled)
        now = datetime.now(timezone.utc)

        next_run_at = existing.next_run_at
        if any(
            k in updates
            for k in ("schedule_type", "interval_seconds", "cron_expression")
        ):
            if enabled:
                try:
                    next_run_at = compute_next_run_at(
                        schedule_type, interval_seconds, cron_expression
                    )
                except (ValueError, TypeError):
                    next_run_at = None

        values: dict[str, Any] = {
            "name": updates.get("name", existing.name),
            "task_names": (
                json.dumps(task_names) if task_names is not None else existing.task_names
            ),
            "args": updates.get("args", existing.args),
            "kwargs": updates.get("kwargs", existing.kwargs),
            "queue": updates.get("queue", existing.queue),
            "schedule_type": schedule_type,
            "interval_seconds": interval_seconds,
            "cron_expression": cron_expression,
            "enabled": enabled,
            "max_run_count": updates.get("max_run_count", existing.max_run_count),
            "next_run_at": next_run_at,
            "updated_at": now,
        }

        await session.execute(
            update(BeatSchedule).where(BeatSchedule.id == beat_id).values(**values)
        )
        await session.commit()

    return JSONResponse({"ok": True})


@router.delete("/{beat_id}", response_model=None, dependencies=[Depends(require_auth)])
async def delete_beat(beat_id: str) -> JSONResponse:
    async with get_session() as session:
        result = await session.execute(
            select(BeatSchedule).where(BeatSchedule.id == beat_id).limit(1)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Beat not found")
        await session.execute(
            delete(BeatSchedule).where(BeatSchedule.id == beat_id)
        )
        await session.commit()
    return JSONResponse({"ok": True})


@router.post("/{beat_id}/toggle", response_model=None, dependencies=[Depends(require_auth)])
async def toggle_beat(beat_id: str) -> JSONResponse:
    async with get_session() as session:
        result = await session.execute(
            select(BeatSchedule).where(BeatSchedule.id == beat_id).limit(1)
        )
        existing = result.scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="Beat not found")

        new_enabled = not existing.enabled
        now = datetime.now(timezone.utc)

        next_run_at = existing.next_run_at
        if new_enabled and not next_run_at:
            try:
                next_run_at = compute_next_run_at(
                    existing.schedule_type,
                    existing.interval_seconds,
                    existing.cron_expression,
                )
            except (ValueError, TypeError):
                pass

        await session.execute(
            update(BeatSchedule)
            .where(BeatSchedule.id == beat_id)
            .values(
                enabled=new_enabled,
                next_run_at=next_run_at if new_enabled else None,
                updated_at=now,
            )
        )
        await session.commit()

    return JSONResponse({"enabled": new_enabled})


@router.post("/{beat_id}/run-now", response_model=None, dependencies=[Depends(require_auth)])
async def run_beat_now(beat_id: str) -> JSONResponse:
    async with get_session() as session:
        result = await session.execute(
            select(BeatSchedule).where(BeatSchedule.id == beat_id).limit(1)
        )
        beat = result.scalar_one_or_none()
        if not beat:
            raise HTTPException(status_code=404, detail="Beat not found")

        task_names: list[str] = json.loads(beat.task_names or "[]")
        if not task_names:
            raise HTTPException(status_code=400, detail="No tasks configured")

        args: list[Any] = json.loads(beat.args or "[]")
        kwargs: dict[str, Any] = json.loads(beat.kwargs or "{}")
        queue = beat.queue or "celery"
        now = datetime.now(timezone.utc)
        dispatched: list[str] = []

        for task_name in task_names:
            task_id: str | None = None
            error: str | None = None
            status = "SENT"

            try:
                task_id = await dispatch_task(task_name, args, kwargs, queue)
                dispatched.append(task_id)
            except Exception as exc:
                error = str(exc)
                status = "FAILURE"

            run = BeatRun(
                id=str(uuid.uuid4()),
                schedule_id=beat.id,
                task_id=task_id,
                task_name=task_name,
                args=beat.args,
                kwargs=beat.kwargs,
                queue=beat.queue,
                status=status,
                error=error,
                scheduled_at=now,
                sent_at=now,
            )
            session.add(run)

        await session.execute(
            update(BeatSchedule)
            .where(BeatSchedule.id == beat.id)
            .values(
                last_run_at=now,
                total_run_count=(beat.total_run_count or 0) + 1,
                updated_at=now,
            )
        )
        await session.commit()

    return JSONResponse({"taskIds": dispatched})


@router.get("/{beat_id}/runs", response_model=list[BeatRunResponse])
async def get_beat_runs(
    beat_id: str,
    limit: int = Query(50, ge=1, le=200),
) -> Any:
    async with get_session() as session:
        result = await session.execute(
            select(BeatRun)
            .where(BeatRun.schedule_id == beat_id)
            .order_by(desc(BeatRun.sent_at))
            .limit(limit)
        )
        return result.scalars().all()
