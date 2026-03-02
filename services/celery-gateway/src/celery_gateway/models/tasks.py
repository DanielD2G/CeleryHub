from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .base import CamelModel


class SendTaskRequest(BaseModel):
    task_name: str
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    queue: str = "celery"
    countdown: float | None = None
    eta: datetime | None = None
    expires: float | datetime | None = None
    priority: int | None = Field(None, ge=0, le=9)
    task_id: str | None = None


class SendTaskResponse(BaseModel):
    task_id: str
    status: str = "PENDING"


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Any = None
    traceback: str | None = None
    date_done: str | None = None
    name: str | None = None
    worker: str | None = None
    runtime: float | None = None


class RevokeRequest(BaseModel):
    terminate: bool = False
    signal: Literal["SIGTERM", "SIGKILL"] = "SIGTERM"


class RevokeResponse(BaseModel):
    task_id: str
    revoked: bool


class ActiveTaskInfo(BaseModel):
    id: str
    name: str
    args: str | None = None
    kwargs: str | None = None
    worker: str
    time_start: float | None = None
    acknowledged: bool = False


class ActiveTasksResponse(BaseModel):
    tasks: list[ActiveTaskInfo]
    by_worker: dict[str, list[ActiveTaskInfo]]


class RegisteredTasksResponse(BaseModel):
    tasks: list[str]
    by_worker: dict[str, list[str]]


# ---------------------------------------------------------------------------
# Frontend-facing models (camelCase responses)
# ---------------------------------------------------------------------------


class FrontendSendTaskRequest(CamelModel):
    task_name: str = Field(min_length=1, pattern=r"^[\w.]+$")
    queue: str = "celery"
    args: str = "[]"
    kwargs: str = "{}"
    countdown: float | None = None
    eta: str | None = None
    priority: int | None = Field(None, ge=0, le=9)

    @field_validator("args")
    @classmethod
    def _validate_args_json(cls, v: str) -> str:
        try:
            parsed = json.loads(v)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("Invalid JSON for args") from exc
        if not isinstance(parsed, list):
            raise ValueError("Args must be a JSON array")
        return v

    @field_validator("kwargs")
    @classmethod
    def _validate_kwargs_json(cls, v: str) -> str:
        try:
            parsed = json.loads(v)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("Invalid JSON for kwargs") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Kwargs must be a JSON object")
        return v


class FrontendSendTaskResponse(CamelModel):
    task_id: str


class FrontendActiveTask(CamelModel):
    task_id: str
    name: str
    worker: str
    started_at: float
    status: Literal["sent", "received", "started"]
    args: str | None = None
    kwargs: str | None = None


class FrontendTaskHistoryItem(CamelModel):
    task_id: str
    name: str
    worker: str
    status: str
    runtime: float | None = None
    result: str | None = None
    traceback: str | None = None
    args: str | None = None
    kwargs: str | None = None
    completed_at: float


class FrontendTaskPayload(CamelModel):
    args: str
    kwargs: str
    queue: str
    timestamp: float


class FrontendRegisteredTasksResult(CamelModel):
    by_worker: dict[str, list[str]]
    tasks: list[str]


class FrontendTaskStatusResponse(CamelModel):
    status: str
    result: Any = None


class FrontendQueueDetailsResult(CamelModel):
    queue_names: list[str]
    depths: dict[str, int]
    pending: dict[str, list[dict[str, str]]]
