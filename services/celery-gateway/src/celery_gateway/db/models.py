from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
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
    enabled: Mapped[bool | None] = mapped_column(Boolean, default=True)
    max_run_count: Mapped[int | None] = mapped_column(Integer, default=None)
    total_run_count: Mapped[int | None] = mapped_column(Integer, default=0)
    last_run_at: Mapped[str | None] = mapped_column(String, default=None)
    next_run_at: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

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
    scheduled_at: Mapped[str | None] = mapped_column(String, default=None)
    sent_at: Mapped[str | None] = mapped_column(String, default=None)

    schedule: Mapped["BeatSchedule"] = relationship(back_populates="runs")

    __table_args__ = (
        Index("idx_beat_runs_schedule_id", "schedule_id"),
    )
