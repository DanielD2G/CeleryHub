from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class BeatSchedule(Base):
    __tablename__ = "beat_schedules"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    task_names: Mapped[str | None] = mapped_column(String, default="[]")
    args: Mapped[str | None] = mapped_column(String, default="[]")
    kwargs: Mapped[str | None] = mapped_column(String, default="{}")
    queue: Mapped[str | None] = mapped_column(String, default="celery")
    schedule_type: Mapped[str] = mapped_column(String, nullable=False)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    cron_expression: Mapped[str | None] = mapped_column(String, default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_run_count: Mapped[int | None] = mapped_column(Integer, default=None)
    total_run_count: Mapped[int | None] = mapped_column(Integer, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    runs: Mapped[list["BeatRun"]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_beat_schedules_next_run", "enabled", "next_run_at"),
    )


class BeatRun(Base):
    __tablename__ = "beat_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    schedule_id: Mapped[str] = mapped_column(
        String, ForeignKey("beat_schedules.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str | None] = mapped_column(String, default=None)
    task_name: Mapped[str | None] = mapped_column(String, default=None)
    args: Mapped[str | None] = mapped_column(String, default=None)
    kwargs: Mapped[str | None] = mapped_column(String, default=None)
    queue: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str | None] = mapped_column(String, default="SENT")
    error: Mapped[str | None] = mapped_column(String, default=None)
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    schedule: Mapped["BeatSchedule"] = relationship(back_populates="runs")

    __table_args__ = (
        Index("idx_beat_runs_schedule_id", "schedule_id"),
    )
