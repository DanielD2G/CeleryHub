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
from ..db.models import NodeRun, Workflow, WorkflowNode, WorkflowRun
from .scheduler import dispatch_task

logger = logging.getLogger(__name__)

_TERMINAL_NODE_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "skipped"})

_workflow_run_locks: dict[str, asyncio.Lock] = {}
_timeout_tasks: dict[str, asyncio.Task[None]] = {}


def _get_run_lock(workflow_run_id: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a specific workflow run."""
    if workflow_run_id not in _workflow_run_locks:
        _workflow_run_locks[workflow_run_id] = asyncio.Lock()
    return _workflow_run_locks[workflow_run_id]


def _cleanup_run_lock(workflow_run_id: str) -> None:
    """Remove the lock for a finished workflow run to prevent memory leaks."""
    _workflow_run_locks.pop(workflow_run_id, None)


async def start_workflow_run(workflow_id: str, *, trigger: str = "manual") -> str:
    """Create a WorkflowRun with NodeRuns for each node, then advance."""
    async with get_session() as session:
        result = await session.execute(
            select(Workflow)
            .options(selectinload(Workflow.nodes))
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

        for node in workflow.nodes:
            node_run = NodeRun(
                id=str(_uuid.uuid4()),
                workflow_run_id=run_id,
                node_id=node.id,
                label=node.label,
                task_name=node.task_name,
                args=node.args,
                kwargs=node.kwargs,
                queue=node.queue,
                status="pending",
            )
            session.add(node_run)

        await session.commit()

    await _advance_workflow(run_id)
    return run_id


async def on_task_completed(
    celery_uuid: str, status: str, *, error: str | None = None
) -> None:
    """Called by event_collector when a Celery task completes. Transition the
    matching NodeRun and advance the workflow."""
    workflow_run_id: str | None = None

    async with get_session() as session:
        result = await session.execute(
            select(NodeRun).where(NodeRun.celery_task_id == celery_uuid).limit(1)
        )
        node_run = result.scalar_one_or_none()
        if node_run is None or node_run.status != "running":
            return

        node_run.status = "succeeded" if status == "SUCCESS" else "failed"
        node_run.finished_at = datetime.now(timezone.utc)
        if error is not None:
            node_run.error = error
        workflow_run_id = node_run.workflow_run_id

        timeout_task = _timeout_tasks.pop(node_run.id, None)
        if timeout_task is not None:
            timeout_task.cancel()

        await session.commit()

    if workflow_run_id:
        await _advance_workflow(workflow_run_id)


async def cancel_workflow_run(workflow_run_id: str) -> bool:
    """Cancel a running workflow run. Returns False if not found or not running."""
    async with get_session() as session:
        result = await session.execute(
            select(WorkflowRun)
            .options(selectinload(WorkflowRun.node_runs))
            .where(WorkflowRun.id == workflow_run_id)
        )
        wf_run = result.scalar_one_or_none()
        if wf_run is None or wf_run.status != "running":
            return False

        now = datetime.now(timezone.utc)
        wf_run.status = "cancelled"
        wf_run.finished_at = now

        for nr in wf_run.node_runs:
            if nr.status in ("pending", "running"):
                nr.status = "skipped"
                nr.finished_at = now
            timeout_task = _timeout_tasks.pop(nr.id, None)
            if timeout_task is not None:
                timeout_task.cancel()

        await session.commit()
        _cleanup_run_lock(workflow_run_id)
    return True


async def _advance_workflow(workflow_run_id: str) -> None:
    """Evaluate pending nodes and dispatch those whose dependencies are met."""
    _run_terminal: bool = False
    async with _get_run_lock(workflow_run_id):
        async with get_session() as session:
            result = await session.execute(
                select(WorkflowRun)
                .options(selectinload(WorkflowRun.node_runs))
                .where(WorkflowRun.id == workflow_run_id)
            )
            wf_run = result.scalar_one_or_none()
            if wf_run is None or wf_run.status != "running":
                return

            # Load node definitions for this workflow
            nodes_result = await session.execute(
                select(WorkflowNode).where(
                    WorkflowNode.workflow_id == wf_run.workflow_id
                )
            )
            node_defs: dict[str, WorkflowNode] = {
                n.id: n for n in nodes_result.scalars().all()
            }

            node_run_by_node_id: dict[str, NodeRun] = {
                nr.node_id: nr for nr in wf_run.node_runs
            }

            had_changes: bool = True
            while had_changes:
                had_changes = False
                for nr in wf_run.node_runs:
                    if nr.status != "pending":
                        continue

                    node_def = node_defs.get(nr.node_id)
                    if node_def is None:
                        nr.status = "skipped"
                        nr.finished_at = datetime.now(timezone.utc)
                        had_changes = True
                        continue

                    dep_ids: list[str] = json.loads(node_def.depends_on or "[]")

                    if not dep_ids:
                        # Root node — dispatch immediately
                        await _dispatch_node(session, nr, node_def)
                        had_changes = True
                        continue

                    # Check if all dependencies are terminal
                    dep_node_runs: list[NodeRun] = [
                        node_run_by_node_id[d]
                        for d in dep_ids
                        if d in node_run_by_node_id
                    ]
                    if len(dep_node_runs) != len(dep_ids):
                        nr.status = "skipped"
                        nr.finished_at = datetime.now(timezone.utc)
                        had_changes = True
                        continue

                    all_deps_terminal: bool = all(
                        d.status in _TERMINAL_NODE_STATUSES for d in dep_node_runs
                    )
                    if not all_deps_terminal:
                        continue

                    # Evaluate condition
                    if _evaluate_condition(node_def.condition, dep_node_runs):
                        await _dispatch_node(session, nr, node_def)
                        had_changes = True
                    else:
                        nr.status = "skipped"
                        nr.finished_at = datetime.now(timezone.utc)
                        had_changes = True

            # Check if workflow run is complete
            all_terminal: bool = all(
                nr.status in _TERMINAL_NODE_STATUSES for nr in wf_run.node_runs
            )
            if all_terminal:
                any_failed: bool = any(
                    nr.status == "failed" for nr in wf_run.node_runs
                )
                wf_run.status = "failed" if any_failed else "succeeded"
                wf_run.finished_at = datetime.now(timezone.utc)
                _run_terminal = True

            await session.commit()

    if _run_terminal:
        _cleanup_run_lock(workflow_run_id)


def _evaluate_condition(condition: str, dep_node_runs: list[NodeRun]) -> bool:
    """Evaluate a node condition against its dependency node runs."""
    if condition == "all_succeeded":
        return all(nr.status == "succeeded" for nr in dep_node_runs)
    if condition == "all_completed":
        return all(nr.status in _TERMINAL_NODE_STATUSES for nr in dep_node_runs)
    if condition == "any_succeeded":
        return any(nr.status == "succeeded" for nr in dep_node_runs)
    if condition == "any_failed":
        return any(nr.status == "failed" for nr in dep_node_runs)
    return False


async def _dispatch_node(
    session: AsyncSession, node_run: NodeRun, node_def: WorkflowNode
) -> None:
    """Dispatch the single task for a node."""
    node_run.status = "running"
    node_run.started_at = datetime.now(timezone.utc)

    args: list[Any] = json.loads(node_def.args or "[]")
    kwargs: dict[str, Any] = json.loads(node_def.kwargs or "{}")
    queue: str = node_def.queue or "celery"

    try:
        celery_task_id = await dispatch_task(
            node_def.task_name, args, kwargs, queue
        )
        node_run.celery_task_id = celery_task_id
    except Exception as exc:
        node_run.status = "failed"
        node_run.error = str(exc)
        node_run.finished_at = datetime.now(timezone.utc)
        return

    if (
        node_def.timeout_seconds
        and node_def.timeout_seconds > 0
        and node_run.status == "running"
    ):
        _timeout_tasks[node_run.id] = asyncio.create_task(
            _handle_node_timeout(
                node_run.id, node_run.workflow_run_id, node_def.timeout_seconds
            )
        )


async def _handle_node_timeout(
    node_run_id: str, workflow_run_id: str, timeout_seconds: int
) -> None:
    """Wait for timeout, then fail the node if still running."""
    await asyncio.sleep(timeout_seconds)
    await _expire_node(node_run_id, workflow_run_id, timeout_seconds)


async def _expire_node(
    node_run_id: str, workflow_run_id: str, timeout_seconds: int
) -> None:
    """Mark a running node as failed due to timeout and advance the workflow."""
    async with get_session() as session:
        result = await session.execute(
            select(NodeRun).where(NodeRun.id == node_run_id).limit(1)
        )
        node_run = result.scalar_one_or_none()
        if node_run is None or node_run.status != "running":
            return

        node_run.status = "failed"
        node_run.error = f"Node timed out after {timeout_seconds}s"
        node_run.finished_at = datetime.now(timezone.utc)

        await session.commit()

    _timeout_tasks.pop(node_run_id, None)
    await _advance_workflow(workflow_run_id)
