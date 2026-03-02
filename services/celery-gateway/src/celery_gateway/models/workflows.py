from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from .base import CamelModel, validate_json_string


class _JsonFieldMixin:
    """Shared validators for args/kwargs JSON string fields."""

    @field_validator("args")
    @classmethod
    def _validate_args_json(cls, v: str | None) -> str | None:
        return validate_json_string(v, "args")

    @field_validator("kwargs")
    @classmethod
    def _validate_kwargs_json(cls, v: str | None) -> str | None:
        return validate_json_string(v, "kwargs")


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class StepInput(_JsonFieldMixin, CamelModel):
    id: str
    label: str = Field(min_length=1)
    task_names: list[str] = Field(min_length=1)
    args: str | None = None
    kwargs: str | None = None
    queue: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    condition: Literal[
        "all_succeeded", "all_completed", "any_succeeded", "any_failed"
    ] = "all_succeeded"


class CreateWorkflowInput(CamelModel):
    name: str = Field(min_length=1)
    description: str | None = None
    schedule_type: Literal["none", "interval", "cron"] = "none"
    interval_seconds: int | None = None
    cron_expression: str | None = None
    enabled: bool = True
    max_run_count: int | None = None
    steps: list[StepInput] = Field(min_length=1)


class UpdateWorkflowInput(CamelModel):
    name: str | None = None
    description: str | None = None
    schedule_type: Literal["none", "interval", "cron"] | None = None
    interval_seconds: int | None = None
    cron_expression: str | None = None
    enabled: bool | None = None
    max_run_count: int | None = None
    steps: list[StepInput] | None = None  # full replace if provided


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class StepResponse(CamelModel):
    id: str
    label: str
    task_names: str
    args: str | None
    kwargs: str | None
    queue: str | None
    depends_on: str
    condition: str


class WorkflowResponse(CamelModel):
    id: str
    name: str
    description: str | None
    schedule_type: str
    interval_seconds: int | None
    cron_expression: str | None
    enabled: bool
    max_run_count: int | None
    total_run_count: int
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    steps: list[StepResponse]


class WorkflowSummaryResponse(CamelModel):
    id: str
    name: str
    description: str | None
    schedule_type: str
    interval_seconds: int | None
    cron_expression: str | None
    enabled: bool
    max_run_count: int | None
    total_run_count: int
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    step_count: int


class TaskRunResponse(CamelModel):
    id: str
    task_id: str | None
    task_name: str
    args: str | None
    kwargs: str | None
    queue: str | None
    status: str
    error: str | None
    sent_at: datetime | None


class StepRunResponse(CamelModel):
    id: str
    step_id: str
    step_label: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    task_runs: list[TaskRunResponse]


class WorkflowRunResponse(CamelModel):
    id: str
    workflow_id: str
    status: str
    trigger: str
    started_at: datetime
    finished_at: datetime | None


class WorkflowRunDetailResponse(CamelModel):
    id: str
    workflow_id: str
    status: str
    trigger: str
    started_at: datetime
    finished_at: datetime | None
    step_runs: list[StepRunResponse]
