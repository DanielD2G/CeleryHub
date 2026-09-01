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


class NodeInput(_JsonFieldMixin, CamelModel):
    id: str
    label: str = Field(min_length=1)
    task_name: str = Field(min_length=1)
    args: str | None = None
    kwargs: str | None = None
    queue: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    condition: Literal[
        "all_succeeded", "all_completed", "any_succeeded", "any_failed"
    ] = "all_succeeded"
    timeout_seconds: int | None = None
    position_x: float | None = None
    position_y: float | None = None


class CreateWorkflowInput(CamelModel):
    name: str = Field(min_length=1)
    description: str | None = None
    schedule_type: Literal["none", "interval", "cron"] = "none"
    interval_seconds: int | None = None
    cron_expression: str | None = None
    enabled: bool = True
    max_run_count: int | None = None
    nodes: list[NodeInput] = Field(min_length=1)


class UpdateWorkflowInput(CamelModel):
    name: str | None = None
    description: str | None = None
    schedule_type: Literal["none", "interval", "cron"] | None = None
    interval_seconds: int | None = None
    cron_expression: str | None = None
    enabled: bool | None = None
    max_run_count: int | None = None
    nodes: list[NodeInput] | None = None  # full replace if provided


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class NodeResponse(CamelModel):
    id: str
    label: str
    task_name: str
    args: str | None
    kwargs: str | None
    queue: str | None
    depends_on: str
    condition: str
    timeout_seconds: int | None
    position_x: float | None
    position_y: float | None


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
    nodes: list[NodeResponse]


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
    node_count: int


class NodeRunResponse(CamelModel):
    id: str
    node_id: str
    label: str
    task_name: str
    celery_task_id: str | None
    status: str
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


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
    node_runs: list[NodeRunResponse]
