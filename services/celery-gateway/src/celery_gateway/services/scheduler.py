from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from functools import partial
from typing import Any

from croniter import croniter
from sqlalchemy import and_, select, update

from ..celery_app import app as celery_app
from ..db import get_session
from ..db.models import Workflow
from .celery_redis import send_celery_task

logger = logging.getLogger(__name__)

_ticking: bool = False

# A due workflow firing later than this is logged as a missed/late run
# (typically the app was down when the schedule came due).
LATE_FIRE_GRACE_SECONDS = 300


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

            stmt = select(Workflow).where(
                and_(
                    Workflow.enabled == True,  # noqa: E712
                    Workflow.schedule_type != "none",
                    Workflow.next_run_at <= now,
                )
            )
            result = await session.execute(stmt)
            due_workflows: list[Workflow] = list(result.scalars().all())

            if due_workflows:
                logger.info(
                    "[CeleryHub Scheduler] %d workflow(s) due", len(due_workflows)
                )

            for workflow in due_workflows:
                if workflow.next_run_at is not None:
                    delay = (now - workflow.next_run_at).total_seconds()
                    if delay > LATE_FIRE_GRACE_SECONDS:
                        logger.warning(
                            "[CeleryHub Scheduler] Workflow '%s' firing %.0fs "
                            "late (was due at %s) — likely downtime",
                            workflow.name,
                            delay,
                            workflow.next_run_at.isoformat(),
                        )
                new_total: int = workflow.total_run_count + 1
                should_disable: bool = (
                    workflow.max_run_count is not None
                    and new_total >= workflow.max_run_count
                )

                next_run_at: datetime | None = None
                if not should_disable:
                    try:
                        next_run_at = compute_next_run_at(
                            workflow.schedule_type,
                            workflow.interval_seconds,
                            workflow.cron_expression,
                        )
                    except (ValueError, TypeError):
                        next_run_at = None

                await session.execute(
                    update(Workflow)
                    .where(Workflow.id == workflow.id)
                    .values(
                        next_run_at=next_run_at,
                        total_run_count=new_total,
                        enabled=False if should_disable else workflow.enabled,
                        last_run_at=now,
                        updated_at=now,
                    )
                )
                await session.commit()

                # Start workflow run outside the update transaction
                from .workflow_engine import start_workflow_run

                try:
                    await start_workflow_run(workflow.id, trigger="scheduled")
                except Exception:
                    logger.exception(
                        "[CeleryHub Scheduler] Failed to start workflow '%s'",
                        workflow.name,
                    )

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
