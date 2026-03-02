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

_workflow_run_locks: dict[str, asyncio.Lock] = {}


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

        all_terminal = all(tr.status in _TERMINAL_TASK_STATUSES for tr in all_task_runs)
        if all_terminal:
            step_run_result = await session.execute(
                select(StepRun).where(StepRun.id == step_run_id).limit(1)
            )
            step_run = step_run_result.scalar_one_or_none()
            if step_run and step_run.status == "running":
                any_failed: bool = any(
                    tr.status == "FAILURE" for tr in all_task_runs
                )
                step_run.status = "failed" if any_failed else "succeeded"
                step_run.finished_at = datetime.now(timezone.utc)
                workflow_run_id = step_run.workflow_run_id

        await session.commit()

    if all_terminal and step_run and workflow_run_id:
        await _advance_workflow(workflow_run_id)


async def cancel_workflow_run(workflow_run_id: str) -> bool:
    """Cancel a running workflow run. Returns False if not found or not running."""
    async with get_session() as session:
        result = await session.execute(
            select(WorkflowRun)
            .options(selectinload(WorkflowRun.step_runs))
            .where(WorkflowRun.id == workflow_run_id)
        )
        wf_run = result.scalar_one_or_none()
        if wf_run is None or wf_run.status != "running":
            return False

        now = datetime.now(timezone.utc)
        wf_run.status = "cancelled"
        wf_run.finished_at = now

        for sr in wf_run.step_runs:
            if sr.status in ("pending", "running"):
                sr.status = "skipped"
                sr.finished_at = now

        await session.commit()
        _cleanup_run_lock(workflow_run_id)
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
