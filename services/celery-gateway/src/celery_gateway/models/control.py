from __future__ import annotations

import re
from typing import Any

from pydantic import Field, field_validator

from .base import CamelModel

_RATE_RE = re.compile(r"^\d+/[smh]$")


class PoolResizeRequest(CamelModel):
    n: int = Field(1, ge=1, le=100)
    workers: list[str] | None = None


class RateLimitRequest(CamelModel):
    task_name: str
    rate: str
    workers: list[str] | None = None

    @field_validator("rate")
    @classmethod
    def _validate_rate(cls, v: str) -> str:
        if not _RATE_RE.match(v):
            raise ValueError("rate must match pattern '<number>/<s|m|h>' e.g. '10/s'")
        return v


class ConsumerRequest(CamelModel):
    queue: str = Field(min_length=1, max_length=255)
    workers: list[str] | None = None


class ShutdownRequest(CamelModel):
    workers: list[str] | None = None


class ControlResponse(CamelModel):
    action: str
    success: bool
    responses: dict[str, Any] = {}
    errors: dict[str, str] = {}
