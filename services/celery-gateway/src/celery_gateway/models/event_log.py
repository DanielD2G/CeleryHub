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
