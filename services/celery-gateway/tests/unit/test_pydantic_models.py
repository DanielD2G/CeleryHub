from __future__ import annotations

import pytest
from pydantic import ValidationError

from celery_gateway.models.workflows import (
    CreateWorkflowInput,
    StepInput,
    UpdateWorkflowInput,
    WorkflowResponse,
    WorkflowRunResponse,
)
from celery_gateway.models.tasks import (
    CamelModel,
    FrontendActiveTask,
    FrontendQueueDetailsResult,
    FrontendSendTaskRequest,
    FrontendTaskStatusResponse,
    SendTaskRequest,
)


class TestCamelModel:
    def test_alias_serialization(self) -> None:
        class Sample(CamelModel):
            task_name: str
            some_value: int

        obj = Sample(task_name="add", some_value=42)
        data = obj.model_dump(by_alias=True)
        assert "taskName" in data
        assert "someValue" in data
        assert data["taskName"] == "add"

    def test_python_field_access(self) -> None:
        class Sample(CamelModel):
            task_name: str

        obj = Sample(task_name="add")
        assert obj.task_name == "add"


class TestFrontendActiveTask:
    def test_valid_status_started(self) -> None:
        task = FrontendActiveTask(
            task_id="abc",
            name="add",
            worker="w1",
            started_at=1234.0,
            status="started",
        )
        assert task.status == "started"

    def test_valid_status_received(self) -> None:
        task = FrontendActiveTask(
            task_id="abc",
            name="add",
            worker="w1",
            started_at=1234.0,
            status="received",
        )
        assert task.status == "received"

    def test_valid_status_sent(self) -> None:
        task = FrontendActiveTask(
            task_id="abc",
            name="add",
            worker="w1",
            started_at=1234.0,
            status="sent",
        )
        assert task.status == "sent"

    def test_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            FrontendActiveTask(
                task_id="abc",
                name="add",
                worker="w1",
                started_at=1234.0,
                status="invalid",  # type: ignore[arg-type]
            )


class TestFrontendSendTaskRequest:
    def test_defaults(self) -> None:
        req = FrontendSendTaskRequest(task_name="add")
        assert req.queue == "celery"
        assert req.args == "[]"
        assert req.kwargs == "{}"
        assert req.countdown is None
        assert req.eta is None
        assert req.priority is None

    def test_camel_alias_input(self) -> None:
        req = FrontendSendTaskRequest.model_validate(
            {"taskName": "tasks.add", "queue": "high"}
        )
        assert req.task_name == "tasks.add"
        assert req.queue == "high"


class TestSendTaskRequest:
    def test_defaults(self) -> None:
        req = SendTaskRequest(task_name="add")
        assert req.args == []
        assert req.kwargs == {}
        assert req.queue == "celery"
        assert req.countdown is None
        assert req.eta is None


class TestCreateWorkflowInput:
    def test_camel_case_input(self) -> None:
        data = {
            "name": "test",
            "scheduleType": "interval",
            "intervalSeconds": 60,
            "steps": [
                {
                    "id": "s1",
                    "label": "Step 1",
                    "taskNames": ["tasks.add"],
                }
            ],
        }
        inp = CreateWorkflowInput.model_validate(data)
        assert inp.schedule_type == "interval"
        assert len(inp.steps) == 1
        assert inp.steps[0].task_names == ["tasks.add"]

    def test_python_field_names(self) -> None:
        inp = CreateWorkflowInput(
            name="test",
            schedule_type="interval",
            interval_seconds=60,
            steps=[
                StepInput(id="s1", label="Step 1", task_names=["a"]),
            ],
        )
        assert inp.schedule_type == "interval"
        assert inp.steps[0].task_names == ["a"]

    def test_optional_fields_default_none(self) -> None:
        inp = CreateWorkflowInput(
            name="test",
            schedule_type="cron",
            steps=[
                StepInput(id="s1", label="Step 1", task_names=["a"]),
            ],
        )
        assert inp.interval_seconds is None
        assert inp.cron_expression is None
        assert inp.max_run_count is None
        assert inp.description is None

    def test_default_schedule_type_none(self) -> None:
        inp = CreateWorkflowInput(
            name="test",
            steps=[
                StepInput(id="s1", label="Step 1", task_names=["a"]),
            ],
        )
        assert inp.schedule_type == "none"
        assert inp.enabled is True

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateWorkflowInput(
                name="",
                steps=[
                    StepInput(id="s1", label="Step 1", task_names=["a"]),
                ],
            )

    def test_empty_steps_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateWorkflowInput(name="test", steps=[])


class TestUpdateWorkflowInput:
    def test_all_optional(self) -> None:
        inp = UpdateWorkflowInput()
        assert inp.name is None
        assert inp.description is None
        assert inp.schedule_type is None
        assert inp.interval_seconds is None
        assert inp.cron_expression is None
        assert inp.enabled is None
        assert inp.steps is None


class TestWorkflowResponse:
    def test_from_attributes(self) -> None:
        class FakeStep:
            id = "step1"
            label = "Step 1"
            task_names = '["add"]'
            args = "[]"
            kwargs = "{}"
            queue = "celery"
            depends_on = "[]"
            condition = "all_succeeded"

        class FakeORM:
            id = "abc"
            name = "test"
            description = None
            schedule_type = "interval"
            interval_seconds = 60
            cron_expression = None
            enabled = True
            max_run_count = None
            total_run_count = 5
            last_run_at = None
            next_run_at = "2025-01-01T00:01:00"
            created_at = "2025-01-01T00:00:00"
            updated_at = "2025-01-01T00:00:00"
            steps = [FakeStep()]

        resp = WorkflowResponse.model_validate(FakeORM(), from_attributes=True)
        assert resp.id == "abc"
        assert resp.total_run_count == 5
        assert resp.interval_seconds == 60
        assert len(resp.steps) == 1
        assert resp.steps[0].id == "step1"


class TestWorkflowRunResponse:
    def test_required_fields(self) -> None:
        run = WorkflowRunResponse(
            id="run1",
            workflow_id="wf1",
            status="running",
            trigger="manual",
            started_at="2025-01-01T00:00:00",
            finished_at=None,
        )
        assert run.status == "running"
        assert run.finished_at is None

    def test_all_fields(self) -> None:
        run = WorkflowRunResponse(
            id="run1",
            workflow_id="wf1",
            status="succeeded",
            trigger="scheduled",
            started_at="2025-01-01T00:00:00",
            finished_at="2025-01-01T00:01:00",
        )
        assert run.status == "succeeded"
        assert run.finished_at is not None


class TestFrontendQueueDetailsResult:
    def test_valid(self) -> None:
        result = FrontendQueueDetailsResult(
            queue_names=["celery", "high"],
            depths={"celery": 5, "high": 0},
            pending={"celery": [{"taskId": "a", "taskName": "add"}], "high": []},
        )
        assert len(result.queue_names) == 2
        assert result.depths["celery"] == 5


class TestFrontendTaskStatusResponse:
    def test_basic(self) -> None:
        resp = FrontendTaskStatusResponse(status="SUCCESS", result="42")
        assert resp.status == "SUCCESS"
        assert resp.result == "42"

    def test_result_none(self) -> None:
        resp = FrontendTaskStatusResponse(status="PENDING")
        assert resp.result is None
