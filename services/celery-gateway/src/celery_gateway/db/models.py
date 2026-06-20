from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
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

    nodes: Mapped[list["WorkflowNode"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )
    runs: Mapped[list["WorkflowRun"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_workflows_schedule", "enabled", "schedule_type", "next_run_at"),
    )


class WorkflowNode(Base):
    __tablename__ = "workflow_nodes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String, nullable=False)
    task_name: Mapped[str] = mapped_column(String, nullable=False)
    args: Mapped[str | None] = mapped_column(String, default="[]")
    kwargs: Mapped[str | None] = mapped_column(String, default="{}")
    queue: Mapped[str | None] = mapped_column(String, default="celery")
    depends_on: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    condition: Mapped[str] = mapped_column(
        String, nullable=False, default="all_succeeded"
    )
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, default=None)

    workflow: Mapped["Workflow"] = relationship(back_populates="nodes")

    __table_args__ = (Index("idx_workflow_nodes_workflow_id", "workflow_id"),)


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
    node_runs: Mapped[list["NodeRun"]] = relationship(
        back_populates="workflow_run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_workflow_runs_workflow_id", "workflow_id"),
        Index("idx_workflow_runs_status", "status"),
    )


class NodeRun(Base):
    __tablename__ = "node_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    task_name: Mapped[str] = mapped_column(String, nullable=False)
    args: Mapped[str | None] = mapped_column(String, default=None)
    kwargs: Mapped[str | None] = mapped_column(String, default=None)
    queue: Mapped[str | None] = mapped_column(String, default=None)
    celery_task_id: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(String, default=None)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="node_runs")

    __table_args__ = (
        Index("idx_node_runs_workflow_run_id", "workflow_run_id"),
        Index("idx_node_runs_celery_task_id", "celery_task_id"),
    )


class CeleryEvent(Base):
    __tablename__ = "celery_events"

    id: Mapped[int] = mapped_column(BigInteger, autoincrement=True)
    event_uid: Mapped[str] = mapped_column(String, nullable=False)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    task_id: Mapped[str | None] = mapped_column(String, default=None)
    task_name: Mapped[str | None] = mapped_column(String, default=None)
    hostname: Mapped[str | None] = mapped_column(String, default=None)
    queue: Mapped[str | None] = mapped_column(String, default=None)
    runtime: Mapped[float | None] = mapped_column(Float, default=None)
    result: Mapped[str | None] = mapped_column(Text, default=None)
    exception: Mapped[str | None] = mapped_column(Text, default=None)
    traceback: Mapped[str | None] = mapped_column(Text, default=None)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Composite PK includes the partition key (required by Postgres for
    # partitioned tables). The actual DDL is authored in the migration;
    # this mapping exists so ORM reads/inserts work.
    __mapper_args__ = {"primary_key": [id, event_time]}


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
