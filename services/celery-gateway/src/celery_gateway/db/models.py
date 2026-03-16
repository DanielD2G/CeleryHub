from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    schedule_type: Mapped[str] = mapped_column(
        String, nullable=False, default="none"
    )  # "none"|"interval"|"cron"
    interval_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    cron_expression: Mapped[str | None] = mapped_column(String, default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_run_count: Mapped[int | None] = mapped_column(Integer, default=None)
    total_run_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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

    steps: Mapped[list["WorkflowStep"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )
    runs: Mapped[list["WorkflowRun"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_workflows_schedule", "enabled", "schedule_type", "next_run_at"),
    )


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String, nullable=False)
    task_names: Mapped[str] = mapped_column(
        String, nullable=False, default="[]"
    )  # JSON
    args: Mapped[str | None] = mapped_column(String, default="[]")
    kwargs: Mapped[str | None] = mapped_column(String, default="{}")
    queue: Mapped[str | None] = mapped_column(String, default="celery")
    depends_on: Mapped[str] = mapped_column(
        String, nullable=False, default="[]"
    )  # JSON list of step IDs
    condition: Mapped[str] = mapped_column(
        String, nullable=False, default="all_succeeded"
    )  # "all_succeeded"|"all_completed"|"any_succeeded"|"any_failed"
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, default=None)

    workflow: Mapped["Workflow"] = relationship(back_populates="steps")

    __table_args__ = (Index("idx_workflow_steps_workflow_id", "workflow_id"),)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="running"
    )  # "running"|"succeeded"|"failed"|"cancelled"
    trigger: Mapped[str] = mapped_column(
        String, nullable=False, default="manual"
    )  # "scheduled"|"manual"
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    workflow: Mapped["Workflow"] = relationship(back_populates="runs")
    step_runs: Mapped[list["StepRun"]] = relationship(
        back_populates="workflow_run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_workflow_runs_workflow_id", "workflow_id"),
        Index("idx_workflow_runs_status", "status"),
    )


class StepRun(Base):
    __tablename__ = "step_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[str] = mapped_column(String, nullable=False)  # denormalized, no FK
    step_label: Mapped[str] = mapped_column(String, nullable=False)  # denormalized
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending"
    )  # "pending"|"running"|"succeeded"|"failed"|"skipped"
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="step_runs")
    task_runs: Mapped[list["TaskRun"]] = relationship(
        back_populates="step_run", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_step_runs_workflow_run_id", "workflow_run_id"),)


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    step_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("step_runs.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str | None] = mapped_column(String, default=None)  # Celery UUID
    task_name: Mapped[str] = mapped_column(String, nullable=False)
    args: Mapped[str | None] = mapped_column(String, default=None)
    kwargs: Mapped[str | None] = mapped_column(String, default=None)
    queue: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="SENT"
    )  # "SENT"|"SUCCESS"|"FAILURE"
    error: Mapped[str | None] = mapped_column(String, default=None)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    step_run: Mapped["StepRun"] = relationship(back_populates="task_runs")

    __table_args__ = (
        Index("idx_task_runs_step_run_id", "step_run_id"),
        Index("idx_task_runs_task_id", "task_id"),
    )
