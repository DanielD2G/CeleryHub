from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from .base import CamelModel


class _JsonFieldMixin:
    """Shared validators for args/kwargs JSON string fields."""

    @field_validator("args")
    @classmethod
    def _validate_args_json(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            json.loads(v)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("Invalid JSON for args") from exc
        return v

    @field_validator("kwargs")
    @classmethod
    def _validate_kwargs_json(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            json.loads(v)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("Invalid JSON for kwargs") from exc
        return v


class CreateBeatInput(_JsonFieldMixin, CamelModel):
    name: str = Field(min_length=1)
    task_names: list[str] = Field(min_length=1)
    args: str | None = None
    kwargs: str | None = None
    queue: str | None = None
    schedule_type: Literal["interval", "cron"]
    interval_seconds: int | None = None
    cron_expression: str | None = None
    enabled: bool | None = None
    max_run_count: int | None = None


class UpdateBeatInput(_JsonFieldMixin, CamelModel):
    name: str | None = None
    task_names: list[str] | None = None
    args: str | None = None
    kwargs: str | None = None
    queue: str | None = None
    schedule_type: str | None = None
    interval_seconds: int | None = None
    cron_expression: str | None = None
    enabled: bool | None = None
    max_run_count: int | None = None


class BeatScheduleResponse(CamelModel):
    id: str
    name: str
    task_names: str
    args: str
    kwargs: str
    queue: str | None
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


class BeatRunResponse(CamelModel):
    id: str
    schedule_id: str
    task_id: str | None
    task_name: str | None
    args: str | None
    kwargs: str | None
    queue: str | None
    status: str
    error: str | None
    scheduled_at: datetime | None
    sent_at: datetime | None
