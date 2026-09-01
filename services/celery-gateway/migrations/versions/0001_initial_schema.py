"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("schedule_type", sa.String(), nullable=False, server_default="none"),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("cron_expression", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_run_count", sa.Integer(), nullable=True),
        sa.Column("total_run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_workflows_schedule",
        "workflows",
        ["enabled", "schedule_type", "next_run_at"],
    )

    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.String(),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("task_names", sa.String(), nullable=False, server_default="[]"),
        sa.Column("args", sa.String(), nullable=True, server_default="[]"),
        sa.Column("kwargs", sa.String(), nullable=True, server_default="{}"),
        sa.Column("queue", sa.String(), nullable=True, server_default="celery"),
        sa.Column("depends_on", sa.String(), nullable=False, server_default="[]"),
        sa.Column(
            "condition", sa.String(), nullable=False, server_default="all_succeeded"
        ),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
    )
    op.create_index(
        "idx_workflow_steps_workflow_id", "workflow_steps", ["workflow_id"]
    )

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.String(),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("trigger", sa.String(), nullable=False, server_default="manual"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_workflow_runs_workflow_id", "workflow_runs", ["workflow_id"])
    op.create_index("idx_workflow_runs_status", "workflow_runs", ["status"])

    op.create_table(
        "step_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "workflow_run_id",
            sa.String(),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column("step_label", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_step_runs_workflow_run_id", "step_runs", ["workflow_run_id"])

    op.create_table(
        "task_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "step_run_id",
            sa.String(),
            sa.ForeignKey("step_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("task_name", sa.String(), nullable=False),
        sa.Column("args", sa.String(), nullable=True),
        sa.Column("kwargs", sa.String(), nullable=True),
        sa.Column("queue", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="SENT"),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_task_runs_step_run_id", "task_runs", ["step_run_id"])
    op.create_index("idx_task_runs_task_id", "task_runs", ["task_id"])


def downgrade() -> None:
    op.drop_table("task_runs")
    op.drop_table("step_runs")
    op.drop_table("workflow_runs")
    op.drop_table("workflow_steps")
    op.drop_table("workflows")
