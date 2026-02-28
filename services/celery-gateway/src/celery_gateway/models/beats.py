from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class CreateBeatInput(CamelModel):
    name: str
    task_names: list[str]
    args: str | None = None
    kwargs: str | None = None
    queue: str | None = None
    schedule_type: str
    interval_seconds: int | None = None
    cron_expression: str | None = None
    enabled: bool | None = None
    max_run_count: int | None = None


class UpdateBeatInput(CamelModel):
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
    last_run_at: str | None
    next_run_at: str | None
    created_at: str
    updated_at: str


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
    scheduled_at: str | None
    sent_at: str | None
