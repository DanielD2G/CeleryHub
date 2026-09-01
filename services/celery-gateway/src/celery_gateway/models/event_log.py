from __future__ import annotations

from datetime import datetime

from .base import CamelModel


class EventLogItem(CamelModel):
    event_time: datetime
    event_type: str
    task_id: str | None = None
    task_name: str | None = None
    hostname: str | None = None
    queue: str | None = None
    runtime: float | None = None


class EventLogPage(CamelModel):
    items: list[EventLogItem]
    next_cursor: datetime | None = None


class RetentionResponse(CamelModel):
    retention_days: int


class RetentionInput(CamelModel):
    retention_days: int


class TaskStatsItem(CamelModel):
    task_name: str
    received: int
    succeeded: int
    failed: int
    failure_rate: float
    runtime_avg: float | None
    runtime_p50: float | None
    runtime_p95: float | None
    runtime_p99: float | None


class TaskStatsResponse(CamelModel):
    since: datetime
    until: datetime
    items: list[TaskStatsItem]


class ExceptionGroupItem(CamelModel):
    task_name: str | None
    exception: str
    count: int
    first_seen: datetime
    last_seen: datetime
    sample_task_id: str | None


class ExceptionGroupsResponse(CamelModel):
    since: datetime
    until: datetime
    items: list[ExceptionGroupItem]


class DailyStatItem(CamelModel):
    day: str
    succeeded: int
    failed: int
    runtime_avg: float | None
    runtime_p50: float | None
    runtime_p95: float | None


class ExceptionHistoryItem(CamelModel):
    task_name: str
    exception: str
    count: int
    first_day: str
    last_day: str
    last_seen: str | None


class AnomalyItem(CamelModel):
    kind: str
    task_name: str
    task_id: str | None
    detected_at: str | None
    detail: str
