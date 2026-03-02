from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class WorkerInspectResponse(BaseModel):
    active: dict[str, list[Any]] | None = None
    registered: dict[str, list[str]] | None = None
    reserved: dict[str, list[Any]] | None = None
    scheduled: dict[str, list[Any]] | None = None
    stats: dict[str, dict[str, Any]] | None = None
    conf: dict[str, dict[str, Any]] | None = None
    active_queues: dict[str, list[Any]] | None = None
    timestamp: str
    cached: bool


class QueueInfo(BaseModel):
    name: str
    depth: int
    consumers: list[str]


class QueuesResponse(BaseModel):
    queues: list[QueueInfo]
