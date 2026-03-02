from __future__ import annotations

import pytest
from pydantic import ValidationError

from celery_gateway.models.beats import (
    BeatRunResponse,
    BeatScheduleResponse,
    CreateBeatInput,
    UpdateBeatInput,
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


class TestCreateBeatInput:
    def test_camel_case_input(self) -> None:
        data = {
            "taskNames": ["tasks.add"],
            "scheduleType": "interval",
            "name": "test",
        }
        inp = CreateBeatInput.model_validate(data)
        assert inp.task_names == ["tasks.add"]
        assert inp.schedule_type == "interval"

    def test_python_field_names(self) -> None:
        inp = CreateBeatInput(
            name="test",
            task_names=["a"],
            schedule_type="interval",
        )
        assert inp.task_names == ["a"]
        assert inp.schedule_type == "interval"

    def test_optional_fields_default_none(self) -> None:
        inp = CreateBeatInput(
            name="test",
            task_names=["a"],
            schedule_type="cron",
        )
        assert inp.interval_seconds is None
        assert inp.cron_expression is None
        assert inp.args is None
        assert inp.kwargs is None
        assert inp.queue is None
        assert inp.max_run_count is None


class TestUpdateBeatInput:
    def test_all_optional(self) -> None:
        inp = UpdateBeatInput()
        assert inp.name is None
        assert inp.task_names is None
        assert inp.schedule_type is None
        assert inp.interval_seconds is None
        assert inp.cron_expression is None
        assert inp.enabled is None


class TestBeatScheduleResponse:
    def test_from_attributes(self) -> None:

        class FakeORM:
            id = "abc"
            name = "test"
            task_names = '["add"]'
            args = "[]"
            kwargs = "{}"
            queue = "celery"
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

        resp = BeatScheduleResponse.model_validate(FakeORM(), from_attributes=True)
        assert resp.id == "abc"
        assert resp.total_run_count == 5
        assert resp.interval_seconds == 60


class TestBeatRunResponse:
    def test_required_and_optional_fields(self) -> None:
        run = BeatRunResponse(
            id="run1",
            schedule_id="sched1",
            task_id=None,
            task_name=None,
            args=None,
            kwargs=None,
            queue=None,
            status="SENT",
            error=None,
            scheduled_at=None,
            sent_at=None,
        )
        assert run.task_id is None
        assert run.task_name is None
        assert run.error is None

    def test_all_fields(self) -> None:
        run = BeatRunResponse(
            id="run1",
            schedule_id="sched1",
            task_id="task1",
            task_name="add",
            args="[1]",
            kwargs="{}",
            queue="celery",
            status="SENT",
            error=None,
            scheduled_at="2025-01-01T00:00:00",
            sent_at="2025-01-01T00:00:00",
        )
        assert run.task_id == "task1"


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
