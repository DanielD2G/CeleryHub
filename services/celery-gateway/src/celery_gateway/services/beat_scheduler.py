from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from functools import partial
from typing import Any

from croniter import croniter
from sqlalchemy import and_, select, update

from ..celery_app import app as celery_app
from ..db import get_session
from ..db.models import BeatRun, BeatSchedule
from .celery_redis import send_celery_task

logger = logging.getLogger(__name__)

_ticking: bool = False


def compute_next_run_at(
    schedule_type: str,
    interval_seconds: int | None,
    cron_expression: str | None,
    from_date: datetime | None = None,
) -> datetime:
    base = from_date or datetime.now(timezone.utc)

    if schedule_type == "interval":
        if not interval_seconds or interval_seconds <= 0:
            raise ValueError("interval_seconds must be a positive number")
        return datetime.fromtimestamp(
            base.timestamp() + interval_seconds, tz=timezone.utc
        )

    if schedule_type == "cron":
        if not cron_expression:
            raise ValueError("cron_expression is required for cron schedules")
        cron = croniter(cron_expression, base)
        next_dt: datetime = cron.get_next(datetime)
        return next_dt.replace(tzinfo=timezone.utc) if next_dt.tzinfo is None else next_dt

    raise ValueError(f"Unknown schedule type: {schedule_type}")


def validate_cron_expression(expr: str) -> str | None:
    try:
        croniter(expr)
        return None
    except (ValueError, KeyError, TypeError) as exc:
        return str(exc)


async def dispatch_task(
    task_name: str,
    args: list[Any],
    kwargs: dict[str, Any],
    queue: str,
) -> str:
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            partial(
                celery_app.send_task,
                task_name,
                args=args,
                kwargs=kwargs,
                queue=queue,
            ),
        )
        return result.id
    except Exception:
        logger.debug(
            "Celery send_task failed for '%s', falling back to Redis", task_name
        )
        return await send_celery_task(task_name, args=args, kwargs=kwargs, queue=queue)


async def _tick() -> None:
    global _ticking

    if _ticking:
        return
    _ticking = True

    try:
        async with get_session() as session:
            now = datetime.now(timezone.utc)

            stmt = select(BeatSchedule).where(
                and_(
                    BeatSchedule.enabled == True,  # noqa: E712
                    BeatSchedule.next_run_at <= now,
                )
            )
            result = await session.execute(stmt)
            due_beats: list[BeatSchedule] = list(result.scalars().all())

            if due_beats:
                logger.info("[CeleryHub Scheduler] %d beat(s) due", len(due_beats))

            for beat in due_beats:
                scheduled_at = beat.next_run_at or now
                task_names: list[str] = json.loads(beat.task_names or "[]")
                args: list[Any] = json.loads(beat.args or "[]")
                kwargs: dict[str, Any] = json.loads(beat.kwargs or "{}")
                queue: str = beat.queue or "celery"

                new_total_run_count: int = (beat.total_run_count or 0) + 1
                should_disable: bool = (
                    beat.max_run_count is not None
                    and new_total_run_count >= beat.max_run_count
                )

                next_run_at: datetime | None = None
                if not should_disable:
                    try:
                        next_run_at = compute_next_run_at(
                            beat.schedule_type,
                            beat.interval_seconds,
                            beat.cron_expression,
                        )
                    except (ValueError, TypeError):
                        next_run_at = None

                await session.execute(
                    update(BeatSchedule)
                    .where(BeatSchedule.id == beat.id)
                    .values(
                        next_run_at=next_run_at,
                        total_run_count=new_total_run_count,
                        enabled=False if should_disable else beat.enabled,
                        updated_at=now,
                    )
                )

                for task_name in task_names:
                    task_id: str | None = None
                    error: str | None = None
                    status: str = "SENT"

                    try:
                        task_id = await dispatch_task(task_name, args, kwargs, queue)
                    except Exception as exc:
                        error = str(exc)
                        status = "FAILURE"

                    sent_at = datetime.now(timezone.utc)
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
                        scheduled_at=scheduled_at,
                        sent_at=sent_at,
                    )
                    session.add(run)

                await session.execute(
                    update(BeatSchedule)
                    .where(BeatSchedule.id == beat.id)
                    .values(last_run_at=datetime.now(timezone.utc))
                )

            await session.commit()

    except Exception:
        logger.exception("[CeleryHub Scheduler] Tick error")
    finally:
        _ticking = False


async def _scheduler_loop() -> None:
    logger.info("[CeleryHub Scheduler] Started")
    try:
        while True:
            await _tick()
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        logger.info("[CeleryHub Scheduler] Stopped")


def start_scheduler() -> asyncio.Task[None]:
    return asyncio.create_task(_scheduler_loop())


async def stop_scheduler(task: asyncio.Task[None]) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
