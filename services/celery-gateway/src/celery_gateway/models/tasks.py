from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SendTaskRequest(BaseModel):
    task_name: str
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    queue: str = "celery"
    countdown: float | None = None
    eta: datetime | None = None
    expires: float | datetime | None = None
    priority: int | None = None
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
    signal: str = "SIGTERM"


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
