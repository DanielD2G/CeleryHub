from __future__ import annotations

import asyncio
import json
import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import get_session
from ..db.models import StepRun, TaskRun, Workflow, WorkflowRun, WorkflowStep
from .scheduler import dispatch_task

logger = logging.getLogger(__name__)

_TERMINAL_STEP_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "skipped"})
_TERMINAL_TASK_STATUSES: frozenset[str] = frozenset({"SUCCESS", "FAILURE"})
# Task rows superseded by an automatic or manual retry; ignored when
# deciding whether a step is complete.
_RETRIED_STATUS = "RETRIED"

_workflow_run_locks: dict[str, asyncio.Lock] = {}
_timeout_tasks: dict[str, asyncio.Task[None]] = {}
# Fire-and-forget tasks (retries) need a strong reference until done — the
# event loop alone holds only a weak one.
_background_tasks: set[asyncio.Task[None]] = set()


def _spawn(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _get_run_lock(workflow_run_id: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a specific workflow run."""
    if workflow_run_id not in _workflow_run_locks:
        _workflow_run_locks[workflow_run_id] = asyncio.Lock()
    return _workflow_run_locks[workflow_run_id]


def _cleanup_run_lock(workflow_run_id: str) -> None:
    """Remove the lock for a finished workflow run to prevent memory leaks."""
    _workflow_run_locks.pop(workflow_run_id, None)


async def start_workflow_run(workflow_id: str, *, trigger: str = "manual") -> str:
    """Create a WorkflowRun with StepRuns for each step, then advance."""
    async with get_session() as session:
        result = await session.execute(
            select(Workflow)
            .options(selectinload(Workflow.steps))
            .where(Workflow.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()
        if workflow is None:
            raise ValueError(f"Workflow '{workflow_id}' not found")

        now = datetime.now(timezone.utc)
        run_id = str(_uuid.uuid4())
        workflow_run = WorkflowRun(
            id=run_id,
            workflow_id=workflow.id,
            status="running",
            trigger=trigger,
            started_at=now,
        )
        session.add(workflow_run)

        for step in workflow.steps:
            step_run = StepRun(
                id=str(_uuid.uuid4()),
                workflow_run_id=run_id,
                step_id=step.id,
                step_label=step.label,
                status="pending",
            )
            session.add(step_run)

        await session.commit()

    await _advance_workflow(run_id)
    return run_id


async def on_task_completed(
    task_uuid: str, status: str, *, error: str | None = None
) -> None:
    """Called by event_collector when a task completes. Updates TaskRun and advances workflow."""
    workflow_run_id: str | None = None
    all_terminal: bool = False
    step_run: StepRun | None = None

    async with get_session() as session:
        result = await session.execute(
            select(TaskRun).where(TaskRun.task_id == task_uuid).limit(1)
        )
        task_run = result.scalar_one_or_none()
        if task_run is None:
            return

        task_run.status = status
        if error is not None:
            task_run.error = error

        # Check if all task runs for this step are terminal
        step_run_id = task_run.step_run_id
        all_task_runs_result = await session.execute(
            select(TaskRun).where(TaskRun.step_run_id == step_run_id)
        )
        all_task_runs = list(all_task_runs_result.scalars().all())

        active = [tr for tr in all_task_runs if tr.status != _RETRIED_STATUS]
        all_terminal = all(tr.status in _TERMINAL_TASK_STATUSES for tr in active)
        retry_scheduled = False
        if all_terminal:
            step_run_result = await session.execute(
                select(StepRun).where(StepRun.id == step_run_id).limit(1)
            )
            step_run = step_run_result.scalar_one_or_none()
            if step_run and step_run.status == "running":
                any_failed: bool = any(
                    tr.status == "FAILURE" for tr in active
                )
                if any_failed:
                    step_def = await session.scalar(
                        select(WorkflowStep)
                        .where(WorkflowStep.id == step_run.step_id)
                        .limit(1)
                    )
                    max_retries = step_def.max_retries if step_def else 0
                    if step_def and step_run.attempt <= max_retries:
                        # Automatic retry: supersede the failed rows, bump the
                        # attempt, and re-dispatch only what failed after the
                        # configured delay. The step stays "running".
                        failed_names = [
                            tr.task_name for tr in active if tr.status == "FAILURE"
                        ]
                        for tr in active:
                            if tr.status == "FAILURE":
                                tr.status = _RETRIED_STATUS
                        step_run.attempt += 1
                        delay = step_def.retry_delay_seconds or 0
                        logger.info(
                            "[CeleryHub Engine] Retrying step '%s' "
                            "(attempt %d/%d, delay %ds): %s",
                            step_run.step_label,
                            step_run.attempt,
                            max_retries + 1,
                            delay,
                            failed_names,
                        )
                        # Timeout budget is per attempt: disarm the current
                        # timer; _retry_step_tasks re-arms it after dispatch.
                        stale_timer = _timeout_tasks.pop(step_run.id, None)
                        if stale_timer is not None:
                            stale_timer.cancel()
                        _spawn(
                            _retry_step_tasks(
                                step_run.id, step_def.id, failed_names, delay
                            )
                        )
                        retry_scheduled = True
                if not retry_scheduled:
                    step_run.status = "failed" if any_failed else "succeeded"
                    step_run.finished_at = datetime.now(timezone.utc)
                    workflow_run_id = step_run.workflow_run_id

                    # Cancel timeout if step completed naturally
                    timeout_task = _timeout_tasks.pop(step_run_id, None)
                    if timeout_task is not None:
                        timeout_task.cancel()

        await session.commit()

    if all_terminal and not retry_scheduled and step_run and workflow_run_id:
        await _advance_workflow(workflow_run_id)


async def _retry_step_tasks(
    step_run_id: str, step_def_id: str, task_names: list[str], delay: int
) -> None:
    """Re-dispatch the failed tasks of a step after the retry delay."""
    if delay > 0:
        await asyncio.sleep(delay)
    async with get_session() as session:
        step_run = await session.scalar(
            select(StepRun).where(StepRun.id == step_run_id).limit(1)
        )
        step_def = await session.scalar(
            select(WorkflowStep).where(WorkflowStep.id == step_def_id).limit(1)
        )
        if step_run is None or step_def is None or step_run.status != "running":
            return
        args: list[Any] = json.loads(step_def.args or "[]")
        kwargs: dict[str, Any] = json.loads(step_def.kwargs or "{}")
        queue: str = step_def.queue or "celery"
        for task_name in task_names:
            task_id: str | None = None
            error: str | None = None
            status: str = "SENT"
            try:
                task_id = await dispatch_task(task_name, args, kwargs, queue)
            except Exception as exc:
                error = str(exc)
                status = "FAILURE"
            session.add(
                TaskRun(
                    id=str(_uuid.uuid4()),
                    step_run_id=step_run.id,
                    task_id=task_id,
                    task_name=task_name,
                    args=step_def.args,
                    kwargs=step_def.kwargs,
                    queue=step_def.queue,
                    status=status,
                    error=error,
                    sent_at=datetime.now(timezone.utc),
                )
            )
        workflow_run_id = step_run.workflow_run_id
        timeout_seconds = step_def.timeout_seconds
        await session.commit()

    # Fresh timeout for this attempt.
    if timeout_seconds and timeout_seconds > 0:
        _timeout_tasks[step_run_id] = asyncio.create_task(
            _handle_step_timeout(step_run_id, workflow_run_id, timeout_seconds)
        )


async def cancel_workflow_run(workflow_run_id: str) -> bool:
    """Cancel a running workflow run. Returns False if not found or not running."""
    in_flight_ids: list[str] = []
    async with get_session() as session:
        result = await session.execute(
            select(WorkflowRun)
            .options(
                selectinload(WorkflowRun.step_runs).selectinload(StepRun.task_runs)
            )
            .where(WorkflowRun.id == workflow_run_id)
        )
        wf_run = result.scalar_one_or_none()
        if wf_run is None or wf_run.status != "running":
            return False

        for sr in wf_run.step_runs:
            for tr in sr.task_runs:
                if (
                    tr.task_id
                    and tr.status not in _TERMINAL_TASK_STATUSES
                    and tr.status != _RETRIED_STATUS
                ):
                    in_flight_ids.append(tr.task_id)

        now = datetime.now(timezone.utc)
        wf_run.status = "cancelled"
        wf_run.finished_at = now

        for sr in wf_run.step_runs:
            if sr.status in ("pending", "running"):
                sr.status = "skipped"
                sr.finished_at = now
            timeout_task = _timeout_tasks.pop(sr.id, None)
            if timeout_task is not None:
                timeout_task.cancel()

        await session.commit()
        _cleanup_run_lock(workflow_run_id)

    if in_flight_ids:
        # Revoke the Celery tasks still in flight so cancel actually stops
        # work instead of just flipping run status.
        try:
            from ..celery_app import app as celery_app

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: celery_app.control.revoke(
                    in_flight_ids, terminate=True
                ),
            )
            logger.info(
                "[CeleryHub Engine] Revoked %d in-flight task(s) for "
                "cancelled run %s",
                len(in_flight_ids),
                workflow_run_id,
            )
        except Exception:
            logger.exception(
                "[CeleryHub Engine] Revoke failed for run %s", workflow_run_id
            )
    return True


async def _advance_workflow(workflow_run_id: str) -> None:
    """Evaluate pending steps and dispatch those whose dependencies are met."""
    _run_terminal: bool = False
    async with _get_run_lock(workflow_run_id):
        async with get_session() as session:
            result = await session.execute(
                select(WorkflowRun)
                .options(
                    selectinload(WorkflowRun.step_runs).selectinload(StepRun.task_runs)
                )
                .where(WorkflowRun.id == workflow_run_id)
            )
            wf_run = result.scalar_one_or_none()
            if wf_run is None or wf_run.status != "running":
                return

            # Load step definitions for this workflow
            steps_result = await session.execute(
                select(WorkflowStep).where(
                    WorkflowStep.workflow_id == wf_run.workflow_id
                )
            )
            step_defs: dict[str, WorkflowStep] = {
                s.id: s for s in steps_result.scalars().all()
            }

            step_run_by_step_id: dict[str, StepRun] = {
                sr.step_id: sr for sr in wf_run.step_runs
            }

            had_changes: bool = True
            while had_changes:
                had_changes = False
                for sr in wf_run.step_runs:
                    if sr.status != "pending":
                        continue

                    step_def = step_defs.get(sr.step_id)
                    if step_def is None:
                        sr.status = "skipped"
                        sr.finished_at = datetime.now(timezone.utc)
                        had_changes = True
                        continue

                    dep_ids: list[str] = json.loads(step_def.depends_on or "[]")

                    if not dep_ids:
                        # Root step — dispatch immediately
                        await _dispatch_step(session, sr, step_def)
                        had_changes = True
                        continue

                    # Check if all dependencies are terminal
                    dep_step_runs: list[StepRun] = [
                        step_run_by_step_id[d]
                        for d in dep_ids
                        if d in step_run_by_step_id
                    ]
                    if len(dep_step_runs) != len(dep_ids):
                        sr.status = "skipped"
                        sr.finished_at = datetime.now(timezone.utc)
                        had_changes = True
                        continue

                    all_deps_terminal: bool = all(
                        d.status in _TERMINAL_STEP_STATUSES for d in dep_step_runs
                    )
                    if not all_deps_terminal:
                        continue

                    # Evaluate condition
                    if _evaluate_condition(step_def.condition, dep_step_runs):
                        await _dispatch_step(session, sr, step_def)
                        had_changes = True
                    else:
                        sr.status = "skipped"
                        sr.finished_at = datetime.now(timezone.utc)
                        had_changes = True

            # Check if workflow run is complete
            all_terminal: bool = all(
                sr.status in _TERMINAL_STEP_STATUSES for sr in wf_run.step_runs
            )
            if all_terminal:
                any_failed: bool = any(
                    sr.status == "failed" for sr in wf_run.step_runs
                )
                wf_run.status = "failed" if any_failed else "succeeded"
                wf_run.finished_at = datetime.now(timezone.utc)
                _run_terminal = True
                if any_failed:
                    failed_labels = [
                        sr.step_label
                        for sr in wf_run.step_runs
                        if sr.status == "failed"
                    ]
                    from .alerts import RULE_WORKFLOW_FAILED, fire_and_forget

                    fire_and_forget(
                        RULE_WORKFLOW_FAILED,
                        wf_run.workflow_id,
                        f"Workflow run {wf_run.id} failed "
                        f"(steps: {', '.join(failed_labels)}).",
                    )

            await session.commit()

    if _run_terminal:
        _cleanup_run_lock(workflow_run_id)


def _evaluate_condition(condition: str, dep_step_runs: list[StepRun]) -> bool:
    """Evaluate a step condition against its dependency step runs."""
    if condition == "all_succeeded":
        return all(sr.status == "succeeded" for sr in dep_step_runs)
    if condition == "all_completed":
        return all(sr.status in _TERMINAL_STEP_STATUSES for sr in dep_step_runs)
    if condition == "any_succeeded":
        return any(sr.status == "succeeded" for sr in dep_step_runs)
    if condition == "any_failed":
        return any(sr.status == "failed" for sr in dep_step_runs)
    return False


async def _dispatch_step(
    session: AsyncSession, step_run: StepRun, step_def: WorkflowStep
) -> None:
    """Dispatch all tasks for a step."""
    step_run.status = "running"
    step_run.started_at = datetime.now(timezone.utc)

    task_names: list[str] = json.loads(step_def.task_names or "[]")
    args: list[Any] = json.loads(step_def.args or "[]")
    kwargs: dict[str, Any] = json.loads(step_def.kwargs or "{}")
    queue: str = step_def.queue or "celery"

    _dispatched: list[TaskRun] = []
    for task_name in task_names:
        task_id: str | None = None
        error: str | None = None
        status: str = "SENT"

        try:
            task_id = await dispatch_task(task_name, args, kwargs, queue)
        except Exception as exc:
            error = str(exc)
            status = "FAILURE"

        task_run = TaskRun(
            id=str(_uuid.uuid4()),
            step_run_id=step_run.id,
            task_id=task_id,
            task_name=task_name,
            args=step_def.args,
            kwargs=step_def.kwargs,
            queue=step_def.queue,
            status=status,
            error=error,
            sent_at=datetime.now(timezone.utc),
        )
        session.add(task_run)
        _dispatched.append(task_run)

    # If all tasks failed immediately during dispatch, mark step as failed
    if task_names and all(tr.status == "FAILURE" for tr in _dispatched):
        step_run.status = "failed"
        step_run.finished_at = datetime.now(timezone.utc)
    elif not task_names:
        step_run.status = "succeeded"
        step_run.finished_at = datetime.now(timezone.utc)

    # Start timeout if configured and step is still running
    if (
        step_def.timeout_seconds
        and step_def.timeout_seconds > 0
        and step_run.status == "running"
    ):
        _timeout_tasks[step_run.id] = asyncio.create_task(
            _handle_step_timeout(
                step_run.id, step_run.workflow_run_id, step_def.timeout_seconds
            )
        )


async def _handle_step_timeout(
    step_run_id: str, workflow_run_id: str, timeout_seconds: int
) -> None:
    """Wait for timeout, then fail the step if still running."""
    await asyncio.sleep(timeout_seconds)
    await _expire_step(step_run_id, workflow_run_id, timeout_seconds)


async def _expire_step(
    step_run_id: str, workflow_run_id: str, timeout_seconds: int
) -> None:
    """Mark a running step as failed due to timeout and advance the workflow."""
    async with get_session() as session:
        result = await session.execute(
            select(StepRun)
            .options(selectinload(StepRun.task_runs))
            .where(StepRun.id == step_run_id)
            .limit(1)
        )
        step_run = result.scalar_one_or_none()
        if step_run is None or step_run.status != "running":
            return

        step_run.status = "failed"
        step_run.finished_at = datetime.now(timezone.utc)

        for tr in step_run.task_runs:
            if tr.status not in _TERMINAL_TASK_STATUSES:
                tr.status = "FAILURE"
                tr.error = f"Step timed out after {timeout_seconds}s"

        await session.commit()

    _timeout_tasks.pop(step_run_id, None)
    await _advance_workflow(workflow_run_id)


async def retry_workflow_run(workflow_run_id: str) -> bool:
    """Re-run the failed portion of a finished run.

    Failed and skipped steps go back to pending (their old task rows are
    superseded), succeeded steps keep their result, and the run resumes
    through the normal advance path. Returns False when the run is not in a
    retryable state.
    """
    async with get_session() as session:
        result = await session.execute(
            select(WorkflowRun)
            .options(
                selectinload(WorkflowRun.step_runs).selectinload(StepRun.task_runs)
            )
            .where(WorkflowRun.id == workflow_run_id)
        )
        wf_run = result.scalar_one_or_none()
        if wf_run is None or wf_run.status not in ("failed", "cancelled"):
            return False

        to_reset = [
            sr for sr in wf_run.step_runs if sr.status in ("failed", "skipped")
        ]
        if not to_reset:
            return False

        for sr in to_reset:
            sr.status = "pending"
            sr.started_at = None
            sr.finished_at = None
            sr.attempt = 1
            for tr in sr.task_runs:
                if tr.status != _RETRIED_STATUS:
                    tr.status = _RETRIED_STATUS

        wf_run.status = "running"
        wf_run.finished_at = None
        await session.commit()

    await _advance_workflow(workflow_run_id)
    return True


async def resume_running_workflows() -> None:
    """Recover in-flight runs after a restart.

    Timeout timers and run locks live in process memory; without this pass a
    step that was "running" when the process died stays running forever and
    its run never terminates. For each running step: re-arm the timeout with
    whatever budget remains (expiring immediately if none), then re-advance
    every running run.
    """
    async with get_session() as session:
        result = await session.execute(
            select(WorkflowRun)
            .options(selectinload(WorkflowRun.step_runs))
            .where(WorkflowRun.status == "running")
        )
        running = list(result.scalars().all())
        if not running:
            return

        step_ids = [
            sr.step_id for run in running for sr in run.step_runs
            if sr.status == "running"
        ]
        defs: dict[str, WorkflowStep] = {}
        if step_ids:
            defs = {
                d.id: d
                for d in (
                    await session.execute(
                        select(WorkflowStep).where(WorkflowStep.id.in_(step_ids))
                    )
                ).scalars()
            }

    logger.info(
        "[CeleryHub Engine] Resuming %d in-flight workflow run(s) after restart",
        len(running),
    )
    now = datetime.now(timezone.utc)
    for run in running:
        for sr in run.step_runs:
            if sr.status != "running":
                continue
            step_def = defs.get(sr.step_id)
            timeout = step_def.timeout_seconds if step_def else None
            if not timeout or timeout <= 0:
                continue
            elapsed = (
                (now - sr.started_at).total_seconds() if sr.started_at else 0.0
            )
            remaining = timeout - elapsed
            if remaining <= 0:
                await _expire_step(sr.id, run.id, timeout)
            else:
                _timeout_tasks[sr.id] = asyncio.create_task(
                    _handle_step_timeout(sr.id, run.id, int(remaining))
                )
        await _advance_workflow(run.id)
