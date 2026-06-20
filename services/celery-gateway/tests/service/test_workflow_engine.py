"""Integration tests for the workflow engine (node-model)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from celery_gateway.db.models import NodeRun, Workflow, WorkflowNode, WorkflowRun
from celery_gateway.services.workflow_engine import (
    on_task_completed,
    start_workflow_run,
)

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workflow_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _seed_workflow(
    session: AsyncSession,
    nodes: list[dict[str, object]],
) -> str:
    """Seed a Workflow + WorkflowNodes into the database, return workflow ID."""
    wf_id = _make_workflow_id()
    now = _now()
    wf = Workflow(
        id=wf_id,
        name="engine-test",
        schedule_type="none",
        enabled=True,
        total_run_count=0,
        created_at=now,
        updated_at=now,
    )
    session.add(wf)
    for node_spec in nodes:
        wn = WorkflowNode(
            id=str(node_spec["id"]),
            workflow_id=wf_id,
            label=str(node_spec.get("label", node_spec["id"])),
            task_name=str(node_spec["task_name"]),
            args="[]",
            kwargs="{}",
            queue="celery",
            depends_on=str(node_spec.get("depends_on", "[]")),
            condition=str(node_spec.get("condition", "all_succeeded")),
            timeout_seconds=None,
        )
        session.add(wn)
    await session.commit()
    return wf_id


# ---------------------------------------------------------------------------
# (a) start_workflow_run creates one NodeRun per node in "pending"
# ---------------------------------------------------------------------------


class TestStartWorkflowRun:
    async def test_creates_node_runs_in_pending(
        self, db_session: AsyncSession
    ) -> None:
        wf_id = await _seed_workflow(
            db_session,
            [
                {"id": "n1", "label": "A", "task_name": "tasks.a"},
                {"id": "n2", "label": "B", "task_name": "tasks.b", "depends_on": '["n1"]'},
            ],
        )

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new_callable=AsyncMock,
            return_value="celery-uuid-x",
        ):
            run_id = await start_workflow_run(wf_id)

        db_session.expire_all()
        result = await db_session.execute(
            select(NodeRun).where(NodeRun.workflow_run_id == run_id)
        )
        node_runs = result.scalars().all()
        # Two nodes → two NodeRuns
        assert len(node_runs) == 2

        # Build dict by node_id for status assertions
        runs_by_node_id = {nr.node_id: nr for nr in node_runs}

        # Root node (n1) is dispatched → status should be "running"
        assert runs_by_node_id["n1"].status == "running"

        # Dependent node (n2) is still gated → status should be "pending"
        assert runs_by_node_id["n2"].status == "pending"

    async def test_workflow_run_is_created(
        self, db_session: AsyncSession
    ) -> None:
        wf_id = await _seed_workflow(
            db_session,
            [{"id": "n1", "label": "A", "task_name": "tasks.a"}],
        )

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new_callable=AsyncMock,
            return_value="celery-uuid-x",
        ):
            run_id = await start_workflow_run(wf_id)

        result = await db_session.execute(
            select(WorkflowRun).where(WorkflowRun.id == run_id).limit(1)
        )
        wf_run = result.scalar_one()
        assert wf_run.workflow_id == wf_id
        assert wf_run.trigger == "manual"


# ---------------------------------------------------------------------------
# (b) Root node (no deps) is dispatched immediately
# ---------------------------------------------------------------------------


class TestRootNodeDispatched:
    async def test_root_node_becomes_running(
        self, db_session: AsyncSession
    ) -> None:
        wf_id = await _seed_workflow(
            db_session,
            [{"id": "root", "label": "Root", "task_name": "tasks.root"}],
        )

        dispatch_mock = AsyncMock(return_value="celery-uuid-root")
        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task", dispatch_mock
        ):
            run_id = await start_workflow_run(wf_id)

        dispatch_mock.assert_awaited_once()

        db_session.expire_all()
        result = await db_session.execute(
            select(NodeRun).where(NodeRun.workflow_run_id == run_id).limit(1)
        )
        nr = result.scalar_one()
        assert nr.status == "running"
        assert nr.celery_task_id == "celery-uuid-root"

    async def test_dependent_node_stays_pending_while_root_running(
        self, db_session: AsyncSession
    ) -> None:
        wf_id = await _seed_workflow(
            db_session,
            [
                {"id": "n1", "label": "Root", "task_name": "tasks.root"},
                {"id": "n2", "label": "Child", "task_name": "tasks.child", "depends_on": '["n1"]'},
            ],
        )

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new_callable=AsyncMock,
            return_value="celery-uuid-root",
        ):
            run_id = await start_workflow_run(wf_id)

        db_session.expire_all()
        result = await db_session.execute(
            select(NodeRun).where(NodeRun.workflow_run_id == run_id)
        )
        node_runs = {nr.node_id: nr for nr in result.scalars().all()}

        # Root node dispatched → running
        assert node_runs["n1"].status == "running"
        # Child still pending while root is running
        assert node_runs["n2"].status == "pending"


# ---------------------------------------------------------------------------
# (c) on_task_completed transitions node and dispatches dependent
# ---------------------------------------------------------------------------


class TestOnTaskCompleted:
    async def test_success_transitions_node_to_succeeded(
        self, db_session: AsyncSession
    ) -> None:
        wf_id = await _seed_workflow(
            db_session,
            [{"id": "n1", "label": "A", "task_name": "tasks.a"}],
        )

        dispatch_mock = AsyncMock(return_value="celery-uuid-1")
        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task", dispatch_mock
        ):
            run_id = await start_workflow_run(wf_id)

        await on_task_completed("celery-uuid-1", "SUCCESS")

        db_session.expire_all()
        result = await db_session.execute(
            select(NodeRun).where(NodeRun.workflow_run_id == run_id).limit(1)
        )
        nr = result.scalar_one()
        assert nr.status == "succeeded"
        assert nr.finished_at is not None

    async def test_failure_transitions_node_to_failed(
        self, db_session: AsyncSession
    ) -> None:
        wf_id = await _seed_workflow(
            db_session,
            [{"id": "n1", "label": "A", "task_name": "tasks.a"}],
        )

        dispatch_mock = AsyncMock(return_value="celery-uuid-fail")
        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task", dispatch_mock
        ):
            run_id = await start_workflow_run(wf_id)

        await on_task_completed("celery-uuid-fail", "FAILURE", error="oops")

        db_session.expire_all()
        result = await db_session.execute(
            select(NodeRun).where(NodeRun.workflow_run_id == run_id).limit(1)
        )
        nr = result.scalar_one()
        assert nr.status == "failed"
        assert nr.error == "oops"

    async def test_success_dispatches_dependent_node(
        self, db_session: AsyncSession
    ) -> None:
        wf_id = await _seed_workflow(
            db_session,
            [
                {"id": "n1", "label": "Root", "task_name": "tasks.root"},
                {"id": "n2", "label": "Child", "task_name": "tasks.child", "depends_on": '["n1"]'},
            ],
        )

        dispatch_mock = AsyncMock(side_effect=["celery-uuid-root", "celery-uuid-child"])
        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task", dispatch_mock
        ):
            run_id = await start_workflow_run(wf_id)
            await on_task_completed("celery-uuid-root", "SUCCESS")

        # dispatch_task should have been called twice — once for root, once for child
        assert dispatch_mock.await_count == 2

        db_session.expire_all()
        result = await db_session.execute(
            select(NodeRun).where(NodeRun.workflow_run_id == run_id)
        )
        node_runs = {nr.node_id: nr for nr in result.scalars().all()}
        assert node_runs["n1"].status == "succeeded"
        assert node_runs["n2"].status == "running"
        assert node_runs["n2"].celery_task_id == "celery-uuid-child"


# ---------------------------------------------------------------------------
# (d) condition="any_failed" gating
# ---------------------------------------------------------------------------


class TestConditionAnyFailed:
    async def test_any_failed_condition_dispatches_when_dep_failed(
        self, db_session: AsyncSession
    ) -> None:
        wf_id = await _seed_workflow(
            db_session,
            [
                {"id": "n1", "label": "Root", "task_name": "tasks.root"},
                {
                    "id": "n2",
                    "label": "OnFail",
                    "task_name": "tasks.on_fail",
                    "depends_on": '["n1"]',
                    "condition": "any_failed",
                },
            ],
        )

        dispatch_mock = AsyncMock(side_effect=["uuid-1", "uuid-2"])
        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task", dispatch_mock
        ):
            run_id = await start_workflow_run(wf_id)
            await on_task_completed("uuid-1", "FAILURE")

        db_session.expire_all()
        result = await db_session.execute(
            select(NodeRun).where(NodeRun.workflow_run_id == run_id)
        )
        node_runs = {nr.node_id: nr for nr in result.scalars().all()}
        # n2 has condition="any_failed" and n1 failed → should be dispatched
        assert node_runs["n2"].status == "running"


# ---------------------------------------------------------------------------
# (e) all_succeeded condition skips node when dep failed
# ---------------------------------------------------------------------------


class TestConditionAllSucceeded:
    async def test_node_skipped_when_dep_failed_under_all_succeeded(
        self, db_session: AsyncSession
    ) -> None:
        wf_id = await _seed_workflow(
            db_session,
            [
                {"id": "n1", "label": "Root", "task_name": "tasks.root"},
                {
                    "id": "n2",
                    "label": "Child",
                    "task_name": "tasks.child",
                    "depends_on": '["n1"]',
                    "condition": "all_succeeded",
                },
            ],
        )

        dispatch_mock = AsyncMock(return_value="uuid-1")
        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task", dispatch_mock
        ):
            run_id = await start_workflow_run(wf_id)
            await on_task_completed("uuid-1", "FAILURE")

        db_session.expire_all()
        result = await db_session.execute(
            select(NodeRun).where(NodeRun.workflow_run_id == run_id)
        )
        node_runs = {nr.node_id: nr for nr in result.scalars().all()}
        # n2 needs all deps to succeed; n1 failed → n2 skipped
        assert node_runs["n2"].status == "skipped"


# ---------------------------------------------------------------------------
# (f) Workflow run reaches terminal state correctly
# ---------------------------------------------------------------------------


class TestWorkflowTermination:
    async def test_single_node_success_completes_workflow(
        self, db_session: AsyncSession
    ) -> None:
        wf_id = await _seed_workflow(
            db_session,
            [{"id": "n1", "label": "A", "task_name": "tasks.a"}],
        )

        dispatch_mock = AsyncMock(return_value="celery-uuid-1")
        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task", dispatch_mock
        ):
            run_id = await start_workflow_run(wf_id)

        await on_task_completed("celery-uuid-1", "SUCCESS")

        db_session.expire_all()
        result = await db_session.execute(
            select(WorkflowRun).where(WorkflowRun.id == run_id).limit(1)
        )
        wf_run = result.scalar_one()
        assert wf_run.status == "succeeded"
        assert wf_run.finished_at is not None

    async def test_single_node_failure_marks_workflow_failed(
        self, db_session: AsyncSession
    ) -> None:
        wf_id = await _seed_workflow(
            db_session,
            [{"id": "n1", "label": "A", "task_name": "tasks.a"}],
        )

        dispatch_mock = AsyncMock(return_value="celery-uuid-fail")
        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task", dispatch_mock
        ):
            run_id = await start_workflow_run(wf_id)

        await on_task_completed("celery-uuid-fail", "FAILURE")

        db_session.expire_all()
        result = await db_session.execute(
            select(WorkflowRun).where(WorkflowRun.id == run_id).limit(1)
        )
        wf_run = result.scalar_one()
        assert wf_run.status == "failed"
        assert wf_run.finished_at is not None

    async def test_all_nodes_complete_marks_workflow_succeeded(
        self, db_session: AsyncSession
    ) -> None:
        """Two-node chain; both succeed → workflow succeeded."""
        wf_id = await _seed_workflow(
            db_session,
            [
                {"id": "n1", "label": "A", "task_name": "tasks.a"},
                {"id": "n2", "label": "B", "task_name": "tasks.b", "depends_on": '["n1"]'},
            ],
        )

        dispatch_mock = AsyncMock(side_effect=["uuid-1", "uuid-2"])
        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task", dispatch_mock
        ):
            run_id = await start_workflow_run(wf_id)
            await on_task_completed("uuid-1", "SUCCESS")
            await on_task_completed("uuid-2", "SUCCESS")

        db_session.expire_all()
        result = await db_session.execute(
            select(WorkflowRun).where(WorkflowRun.id == run_id).limit(1)
        )
        wf_run = result.scalar_one()
        assert wf_run.status == "succeeded"
        assert wf_run.finished_at is not None

    async def test_skipped_nodes_do_not_prevent_completion(
        self, db_session: AsyncSession
    ) -> None:
        """When a node is skipped, the workflow should still complete."""
        wf_id = await _seed_workflow(
            db_session,
            [
                {"id": "n1", "label": "A", "task_name": "tasks.a"},
                {
                    "id": "n2",
                    "label": "B",
                    "task_name": "tasks.b",
                    "depends_on": '["n1"]',
                    "condition": "all_succeeded",
                },
            ],
        )

        dispatch_mock = AsyncMock(return_value="uuid-fail")
        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task", dispatch_mock
        ):
            run_id = await start_workflow_run(wf_id)
            await on_task_completed("uuid-fail", "FAILURE")

        db_session.expire_all()
        result = await db_session.execute(
            select(WorkflowRun).where(WorkflowRun.id == run_id).limit(1)
        )
        wf_run = result.scalar_one()
        # n1 failed → n2 skipped → workflow failed (any_failed check)
        assert wf_run.status == "failed"
        assert wf_run.finished_at is not None
