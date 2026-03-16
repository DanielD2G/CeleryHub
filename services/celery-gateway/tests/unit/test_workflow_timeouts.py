"""Tests for workflow step timeout logic."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from celery_gateway.db.models import StepRun, TaskRun, Workflow, WorkflowRun, WorkflowStep
from celery_gateway.services.workflow_engine import (
    _expire_step,
    _timeout_tasks,
    cancel_workflow_run,
    on_task_completed,
    start_workflow_run,
)

pytestmark = pytest.mark.asyncio


def _make_workflow(session: AsyncSession, *, timeout: int | None = None) -> str:
    """Create a simple 2-step workflow and return its ID."""
    wf_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    wf = Workflow(
        id=wf_id,
        name="timeout-test",
        schedule_type="none",
        enabled=True,
        total_run_count=0,
        created_at=now,
        updated_at=now,
    )
    step = WorkflowStep(
        id="step-1",
        workflow_id=wf_id,
        label="Step 1",
        task_names='["my_task"]',
        args="[]",
        kwargs="{}",
        queue="celery",
        depends_on="[]",
        condition="all_succeeded",
        timeout_seconds=timeout,
    )
    session.add(wf)
    session.add(step)
    return wf_id


class TestStepTimeout:
    async def test_no_timeout_does_not_schedule_task(
        self, db_session: AsyncSession
    ) -> None:
        """Step without timeout should not create a timeout asyncio.Task."""
        wf_id = _make_workflow(db_session, timeout=None)
        await db_session.commit()

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new_callable=AsyncMock,
            return_value="task-uuid-1",
        ):
            run_id = await start_workflow_run(wf_id)

        # No timeout tasks should exist for any step in this run
        result = await db_session.execute(
            select(StepRun).where(StepRun.workflow_run_id == run_id)
        )
        for sr in result.scalars().all():
            assert sr.id not in _timeout_tasks

    async def test_timeout_schedules_task(
        self, db_session: AsyncSession
    ) -> None:
        """Step with timeout should create an asyncio.Task in _timeout_tasks."""
        wf_id = _make_workflow(db_session, timeout=300)
        await db_session.commit()

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new_callable=AsyncMock,
            return_value="task-uuid-1",
        ):
            run_id = await start_workflow_run(wf_id)

        result = await db_session.execute(
            select(StepRun).where(StepRun.workflow_run_id == run_id)
        )
        step_run = result.scalar_one()
        assert step_run.id in _timeout_tasks
        assert not _timeout_tasks[step_run.id].done()

        # Cleanup
        _timeout_tasks[step_run.id].cancel()
        _timeout_tasks.pop(step_run.id, None)

    async def test_natural_completion_cancels_timeout(
        self, db_session: AsyncSession
    ) -> None:
        """When a step completes naturally, its timeout task should be cancelled."""
        wf_id = _make_workflow(db_session, timeout=300)
        await db_session.commit()

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new_callable=AsyncMock,
            return_value="task-uuid-1",
        ):
            run_id = await start_workflow_run(wf_id)

        result = await db_session.execute(
            select(StepRun).where(StepRun.workflow_run_id == run_id)
        )
        step_run = result.scalar_one()
        assert step_run.id in _timeout_tasks
        timeout_task = _timeout_tasks[step_run.id]

        # Simulate task completion
        await on_task_completed("task-uuid-1", "SUCCESS")

        assert timeout_task.cancelled()
        assert step_run.id not in _timeout_tasks

    async def test_cancel_workflow_cancels_timeout(
        self, db_session: AsyncSession
    ) -> None:
        """Cancelling a workflow run should cancel all timeout tasks."""
        wf_id = _make_workflow(db_session, timeout=300)
        await db_session.commit()

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new_callable=AsyncMock,
            return_value="task-uuid-1",
        ):
            run_id = await start_workflow_run(wf_id)

        result = await db_session.execute(
            select(StepRun).where(StepRun.workflow_run_id == run_id)
        )
        step_run = result.scalar_one()
        assert step_run.id in _timeout_tasks
        timeout_task = _timeout_tasks[step_run.id]

        await cancel_workflow_run(run_id)

        assert timeout_task.cancelled()
        assert step_run.id not in _timeout_tasks

    async def test_timeout_fires_marks_step_failed(
        self, db_session: AsyncSession
    ) -> None:
        """When timeout fires, step should be marked failed with timeout error."""
        wf_id = _make_workflow(db_session, timeout=300)
        await db_session.commit()

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new_callable=AsyncMock,
            return_value="task-uuid-1",
        ):
            run_id = await start_workflow_run(wf_id)

        result = await db_session.execute(
            select(StepRun).where(StepRun.workflow_run_id == run_id)
        )
        step_run = result.scalar_one()
        step_run_id = step_run.id

        # Cancel the real timeout (uses long sleep) and call handler directly
        _timeout_tasks.pop(step_run_id).cancel()

        await _expire_step(step_run_id, run_id, 300)

        # Reload from fresh query (expire cache first)
        db_session.expire_all()
        result = await db_session.execute(
            select(StepRun).where(StepRun.id == step_run_id).limit(1)
        )
        sr = result.scalar_one()
        assert sr.status == "failed"
        assert sr.finished_at is not None

        # Task runs should be marked as FAILURE with timeout error
        tr_result = await db_session.execute(
            select(TaskRun).where(TaskRun.step_run_id == step_run_id)
        )
        for tr in tr_result.scalars().all():
            assert tr.status == "FAILURE"
            assert "timed out after 300s" in tr.error

    async def test_timeout_advances_workflow(
        self, db_session: AsyncSession
    ) -> None:
        """After timeout, the workflow should advance (mark run as failed)."""
        wf_id = _make_workflow(db_session, timeout=300)
        await db_session.commit()

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new_callable=AsyncMock,
            return_value="task-uuid-1",
        ):
            run_id = await start_workflow_run(wf_id)

        result = await db_session.execute(
            select(StepRun).where(StepRun.workflow_run_id == run_id)
        )
        step_run = result.scalar_one()
        _timeout_tasks.pop(step_run.id).cancel()

        await _expire_step(step_run.id, run_id, 300)

        # Workflow run should be marked as failed
        db_session.expire_all()
        run_result = await db_session.execute(
            select(WorkflowRun).where(WorkflowRun.id == run_id).limit(1)
        )
        wf_run = run_result.scalar_one()
        assert wf_run.status == "failed"
        assert wf_run.finished_at is not None

    async def test_timeout_on_already_completed_step_is_noop(
        self, db_session: AsyncSession
    ) -> None:
        """If step already completed when timeout fires, nothing should happen."""
        wf_id = _make_workflow(db_session, timeout=300)
        await db_session.commit()

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new_callable=AsyncMock,
            return_value="task-uuid-1",
        ):
            run_id = await start_workflow_run(wf_id)

        result = await db_session.execute(
            select(StepRun).where(StepRun.workflow_run_id == run_id)
        )
        step_run = result.scalar_one()
        step_run_id = step_run.id
        _timeout_tasks.pop(step_run_id).cancel()

        # Complete the step first
        await on_task_completed("task-uuid-1", "SUCCESS")

        # Now fire timeout — should be a no-op
        await _expire_step(step_run_id, run_id, 300)

        db_session.expire_all()
        result = await db_session.execute(
            select(StepRun).where(StepRun.id == step_run_id).limit(1)
        )
        sr = result.scalar_one()
        assert sr.status == "succeeded"
