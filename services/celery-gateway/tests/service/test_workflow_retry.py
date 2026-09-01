"""Automatic retry policy, manual retry-from-failed, and cancel-with-revoke."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from celery_gateway.db.models import (
    StepRun,
    TaskRun,
    Workflow,
    WorkflowRun,
    WorkflowStep,
)
from celery_gateway.services.workflow_engine import (
    cancel_workflow_run,
    on_task_completed,
    retry_workflow_run,
    start_workflow_run,
)

pytestmark = pytest.mark.asyncio


def _make_workflow(
    session: AsyncSession, *, max_retries: int = 0, retry_delay: int | None = None
) -> str:
    wf_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    session.add(Workflow(
        id=wf_id, name="retry-test", schedule_type="none", enabled=True,
        total_run_count=0, created_at=now, updated_at=now,
    ))
    session.add(WorkflowStep(
        id=f"step-{wf_id}", workflow_id=wf_id, label="Step 1",
        task_names='["my_task"]', args="[]", kwargs="{}", queue="celery",
        depends_on="[]", condition="all_succeeded",
        max_retries=max_retries, retry_delay_seconds=retry_delay,
    ))
    return wf_id


async def _task_id(db_session: AsyncSession, run_id: str, *, exclude: set[str] = frozenset()) -> str:
    rows = (await db_session.execute(
        select(TaskRun).join(StepRun, TaskRun.step_run_id == StepRun.id)
        .where(StepRun.workflow_run_id == run_id)
    )).scalars().all()
    for tr in rows:
        if tr.task_id and tr.task_id not in exclude and tr.status == "SENT":
            return tr.task_id
    raise AssertionError("no SENT task run found")


class TestAutomaticRetry:
    async def test_failed_task_is_retried_then_succeeds(self, db_session):
        wf_id = _make_workflow(db_session, max_retries=1, retry_delay=0)
        await db_session.commit()

        sent: list[str] = []

        async def _dispatch(name, args, kwargs, queue):
            tid = f"celery-{len(sent)}"
            sent.append(tid)
            return tid

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new=AsyncMock(side_effect=_dispatch),
        ):
            run_id = await start_workflow_run(wf_id)
            # First attempt fails -> retry scheduled
            await on_task_completed(sent[0], "FAILURE", error="boom")
            await asyncio.sleep(0.05)  # let the retry task run
            assert len(sent) == 2, "expected a re-dispatch"
            # Retry succeeds
            await on_task_completed(sent[1], "SUCCESS")

        run = await db_session.get(WorkflowRun, run_id)
        await db_session.refresh(run)
        assert run.status == "succeeded"

        step_run = (await db_session.execute(
            select(StepRun).where(StepRun.workflow_run_id == run_id)
        )).scalars().one()
        assert step_run.attempt == 2
        statuses = sorted(
            tr.status for tr in (await db_session.execute(
                select(TaskRun).where(TaskRun.step_run_id == step_run.id)
            )).scalars()
        )
        assert statuses == ["RETRIED", "SUCCESS"]

    async def test_retries_exhausted_marks_step_failed(self, db_session):
        wf_id = _make_workflow(db_session, max_retries=1, retry_delay=0)
        await db_session.commit()

        sent: list[str] = []

        async def _dispatch(name, args, kwargs, queue):
            tid = f"celery-{len(sent)}"
            sent.append(tid)
            return tid

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new=AsyncMock(side_effect=_dispatch),
        ):
            run_id = await start_workflow_run(wf_id)
            await on_task_completed(sent[0], "FAILURE", error="boom")
            await asyncio.sleep(0.05)
            await on_task_completed(sent[1], "FAILURE", error="boom again")
            await asyncio.sleep(0.05)

        assert len(sent) == 2, "no third dispatch after retries exhausted"
        run = await db_session.get(WorkflowRun, run_id)
        await db_session.refresh(run)
        assert run.status == "failed"

    async def test_no_retry_when_policy_zero(self, db_session):
        wf_id = _make_workflow(db_session, max_retries=0)
        await db_session.commit()
        sent: list[str] = []

        async def _dispatch(name, args, kwargs, queue):
            tid = f"celery-{len(sent)}"
            sent.append(tid)
            return tid

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new=AsyncMock(side_effect=_dispatch),
        ):
            run_id = await start_workflow_run(wf_id)
            await on_task_completed(sent[0], "FAILURE", error="boom")
            await asyncio.sleep(0.05)

        assert len(sent) == 1
        run = await db_session.get(WorkflowRun, run_id)
        await db_session.refresh(run)
        assert run.status == "failed"


class TestManualRetry:
    async def test_retry_failed_run_resets_and_redispatches(self, db_session):
        wf_id = _make_workflow(db_session)
        await db_session.commit()
        sent: list[str] = []

        async def _dispatch(name, args, kwargs, queue):
            tid = f"celery-{len(sent)}"
            sent.append(tid)
            return tid

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new=AsyncMock(side_effect=_dispatch),
        ):
            run_id = await start_workflow_run(wf_id)
            await on_task_completed(sent[0], "FAILURE", error="boom")
            run = await db_session.get(WorkflowRun, run_id)
            await db_session.refresh(run)
            assert run.status == "failed"

            assert await retry_workflow_run(run_id) is True
            assert len(sent) == 2
            await on_task_completed(sent[1], "SUCCESS")

        await db_session.refresh(run)
        assert run.status == "succeeded"

    async def test_retry_rejects_running_run(self, db_session):
        wf_id = _make_workflow(db_session)
        await db_session.commit()
        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new=AsyncMock(return_value="tid-1"),
        ):
            run_id = await start_workflow_run(wf_id)
        assert await retry_workflow_run(run_id) is False


class TestCancelRevokes:
    async def test_cancel_revokes_in_flight_tasks(self, db_session):
        wf_id = _make_workflow(db_session)
        await db_session.commit()
        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new=AsyncMock(return_value="tid-inflight"),
        ):
            run_id = await start_workflow_run(wf_id)

        mock_celery = MagicMock()
        with patch("celery_gateway.celery_app.app", mock_celery):
            assert await cancel_workflow_run(run_id) is True
            await asyncio.sleep(0.05)

        mock_celery.control.revoke.assert_called_once()
        args, kwargs = mock_celery.control.revoke.call_args
        assert args[0] == ["tid-inflight"]
        assert kwargs.get("terminate") is True
