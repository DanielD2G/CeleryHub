from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import delete, desc, select, update

from ..db import get_session
from ..db.models import BeatRun, BeatSchedule
from ..services.beat_scheduler import (
    compute_next_run_at,
    validate_cron_expression,
    dispatch_task,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/beats", tags=["beats"])


def _schedule_to_dict(beat: BeatSchedule) -> dict[str, Any]:
    return {
        "id": beat.id,
        "name": beat.name,
        "taskNames": beat.task_names,
        "args": beat.args,
        "kwargs": beat.kwargs,
        "queue": beat.queue,
        "scheduleType": beat.schedule_type,
        "intervalSeconds": beat.interval_seconds,
        "cronExpression": beat.cron_expression,
        "enabled": beat.enabled,
        "maxRunCount": beat.max_run_count,
        "totalRunCount": beat.total_run_count,
        "lastRunAt": beat.last_run_at,
        "nextRunAt": beat.next_run_at,
        "createdAt": beat.created_at,
        "updatedAt": beat.updated_at,
    }


def _run_to_dict(run: BeatRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "scheduleId": run.schedule_id,
        "taskId": run.task_id,
        "taskName": run.task_name,
        "args": run.args,
        "kwargs": run.kwargs,
        "queue": run.queue,
        "status": run.status,
        "error": run.error,
        "scheduledAt": run.scheduled_at,
        "sentAt": run.sent_at,
    }


@router.get("/")
async def list_beats() -> list[dict[str, Any]]:
    async with get_session() as session:
        result = await session.execute(
            select(BeatSchedule).order_by(desc(BeatSchedule.created_at))
        )
        beats = result.scalars().all()
        return [_schedule_to_dict(b) for b in beats]


@router.post("/", response_model=None)
async def create_beat(body: dict[str, Any]) -> JSONResponse:
    name: str = body.get("name", "")
    task_names: list[str] = body.get("taskNames", [])
    args_raw: str = body.get("args", "[]") or "[]"
    kwargs_raw: str = body.get("kwargs", "{}") or "{}"
    queue: str = body.get("queue", "celery") or "celery"
    schedule_type: str = body.get("scheduleType", "")
    interval_seconds: int | None = body.get("intervalSeconds")
    cron_expression: str | None = body.get("cronExpression")
    enabled: bool = body.get("enabled", True) is not False
    max_run_count: int | None = body.get("maxRunCount")

    if not name:
        return JSONResponse({"error": "Name is required"}, status_code=400)
    if not task_names:
        return JSONResponse(
            {"error": "At least one task must be selected"}, status_code=400
        )

    if schedule_type == "interval":
        if not interval_seconds or interval_seconds <= 0:
            return JSONResponse(
                {"error": "Interval seconds must be a positive number"},
                status_code=400,
            )
    elif schedule_type == "cron":
        if not cron_expression:
            return JSONResponse(
                {"error": "Cron expression is required"}, status_code=400
            )
        cron_error = validate_cron_expression(cron_expression)
        if cron_error:
            return JSONResponse(
                {"error": f"Invalid cron: {cron_error}"}, status_code=400
            )
    else:
        return JSONResponse(
            {"error": "Schedule type must be 'interval' or 'cron'"},
            status_code=400,
        )

    try:
        if args_raw:
            json.loads(args_raw)
    except (json.JSONDecodeError, TypeError):
        return JSONResponse({"error": "Invalid JSON for args"}, status_code=400)

    try:
        if kwargs_raw:
            json.loads(kwargs_raw)
    except (json.JSONDecodeError, TypeError):
        return JSONResponse({"error": "Invalid JSON for kwargs"}, status_code=400)

    beat_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    next_run_at: str | None = None
    if enabled:
        try:
            next_run_at = compute_next_run_at(
                schedule_type, interval_seconds, cron_expression
            ).isoformat()
        except (ValueError, TypeError) as exc:
            return JSONResponse(
                {"error": f"Failed to compute next run: {exc}"}, status_code=400
            )

    async with get_session() as session:
        beat = BeatSchedule(
            id=beat_id,
            name=name,
            task_names=json.dumps(task_names),
            args=args_raw,
            kwargs=kwargs_raw,
            queue=queue,
            schedule_type=schedule_type,
            interval_seconds=interval_seconds,
            cron_expression=cron_expression,
            enabled=enabled,
            max_run_count=max_run_count,
            total_run_count=0,
            next_run_at=next_run_at,
            created_at=now,
            updated_at=now,
        )
        session.add(beat)
        await session.commit()

    return JSONResponse({"id": beat_id}, status_code=201)


@router.get("/{beat_id}", response_model=None)
async def get_beat(beat_id: str) -> JSONResponse:
    async with get_session() as session:
        result = await session.execute(
            select(BeatSchedule).where(BeatSchedule.id == beat_id).limit(1)
        )
        beat = result.scalar_one_or_none()
        if not beat:
            return JSONResponse({"error": "Beat not found"}, status_code=404)
        return JSONResponse(_schedule_to_dict(beat))


@router.put("/{beat_id}", response_model=None)
async def update_beat(beat_id: str, body: dict[str, Any]) -> JSONResponse:
    async with get_session() as session:
        result = await session.execute(
            select(BeatSchedule).where(BeatSchedule.id == beat_id).limit(1)
        )
        existing = result.scalar_one_or_none()
        if not existing:
            return JSONResponse({"error": "Beat not found"}, status_code=404)

        task_names = body.get("taskNames")
        if task_names is not None and len(task_names) == 0:
            return JSONResponse(
                {"error": "At least one task must be selected"}, status_code=400
            )

        schedule_type = body.get("scheduleType", existing.schedule_type)
        interval_seconds = (
            body["intervalSeconds"]
            if "intervalSeconds" in body
            else existing.interval_seconds
        )
        cron_expression = (
            body["cronExpression"]
            if "cronExpression" in body
            else existing.cron_expression
        )

        if schedule_type == "cron" and cron_expression:
            cron_error = validate_cron_expression(cron_expression)
            if cron_error:
                return JSONResponse(
                    {"error": f"Invalid cron: {cron_error}"}, status_code=400
                )

        if "args" in body:
            try:
                json.loads(body["args"])
            except (json.JSONDecodeError, TypeError):
                return JSONResponse(
                    {"error": "Invalid JSON for args"}, status_code=400
                )

        if "kwargs" in body:
            try:
                json.loads(body["kwargs"])
            except (json.JSONDecodeError, TypeError):
                return JSONResponse(
                    {"error": "Invalid JSON for kwargs"}, status_code=400
                )

        enabled = body.get("enabled", existing.enabled)
        now = datetime.now(timezone.utc).isoformat()

        next_run_at = existing.next_run_at
        if any(
            k in body for k in ("scheduleType", "intervalSeconds", "cronExpression")
        ):
            if enabled:
                try:
                    next_run_at = compute_next_run_at(
                        schedule_type, interval_seconds, cron_expression
                    ).isoformat()
                except (ValueError, TypeError):
                    next_run_at = None

        values: dict[str, Any] = {
            "name": body.get("name", existing.name),
            "task_names": (
                json.dumps(task_names) if task_names is not None else existing.task_names
            ),
            "args": body.get("args", existing.args),
            "kwargs": body.get("kwargs", existing.kwargs),
            "queue": body.get("queue", existing.queue),
            "schedule_type": schedule_type,
            "interval_seconds": interval_seconds,
            "cron_expression": cron_expression,
            "enabled": enabled,
            "max_run_count": (
                body["maxRunCount"] if "maxRunCount" in body else existing.max_run_count
            ),
            "next_run_at": next_run_at,
            "updated_at": now,
        }

        await session.execute(
            update(BeatSchedule).where(BeatSchedule.id == beat_id).values(**values)
        )
        await session.commit()

    return JSONResponse({"ok": True})


@router.delete("/{beat_id}", response_model=None)
async def delete_beat(beat_id: str) -> JSONResponse:
    async with get_session() as session:
        await session.execute(
            delete(BeatSchedule).where(BeatSchedule.id == beat_id)
        )
        await session.commit()
    return JSONResponse({"ok": True})


@router.post("/{beat_id}/toggle", response_model=None)
async def toggle_beat(beat_id: str) -> JSONResponse:
    async with get_session() as session:
        result = await session.execute(
            select(BeatSchedule).where(BeatSchedule.id == beat_id).limit(1)
        )
        existing = result.scalar_one_or_none()
        if not existing:
            return JSONResponse({"error": "Beat not found"}, status_code=404)

        new_enabled = not existing.enabled
        now = datetime.now(timezone.utc).isoformat()

        next_run_at = existing.next_run_at
        if new_enabled and not next_run_at:
            try:
                next_run_at = compute_next_run_at(
                    existing.schedule_type,
                    existing.interval_seconds,
                    existing.cron_expression,
                ).isoformat()
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


@router.post("/{beat_id}/run-now", response_model=None)
async def run_beat_now(beat_id: str) -> JSONResponse:
    async with get_session() as session:
        result = await session.execute(
            select(BeatSchedule).where(BeatSchedule.id == beat_id).limit(1)
        )
        beat = result.scalar_one_or_none()
        if not beat:
            return JSONResponse({"error": "Beat not found"}, status_code=404)

        task_names: list[str] = json.loads(beat.task_names or "[]")
        if not task_names:
            return JSONResponse(
                {"error": "No tasks configured"}, status_code=400
            )

        args: list[Any] = json.loads(beat.args or "[]")
        kwargs: dict[str, Any] = json.loads(beat.kwargs or "{}")
        queue = beat.queue or "celery"
        now = datetime.now(timezone.utc).isoformat()
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


@router.get("/{beat_id}/runs")
async def get_beat_runs(
    beat_id: str,
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, Any]]:
    async with get_session() as session:
        result = await session.execute(
            select(BeatRun)
            .where(BeatRun.schedule_id == beat_id)
            .order_by(desc(BeatRun.sent_at))
            .limit(limit)
        )
        runs = result.scalars().all()
        return [_run_to_dict(r) for r in runs]
