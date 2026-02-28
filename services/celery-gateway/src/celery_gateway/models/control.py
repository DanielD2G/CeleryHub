from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PoolResizeRequest(BaseModel):
    n: int = 1
    workers: list[str] | None = None


class RateLimitRequest(BaseModel):
    task_name: str
    rate: str
    workers: list[str] | None = None


class ConsumerRequest(BaseModel):
    queue: str
    workers: list[str] | None = None


class ShutdownRequest(BaseModel):
    workers: list[str] | None = None


class ControlResponse(BaseModel):
    action: str
    success: bool
    responses: dict[str, Any] = {}
    errors: dict[str, str] = {}
