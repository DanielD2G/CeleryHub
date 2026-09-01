"""alerts, retry policy, dead-man's switch, exception rollup

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Retry policy per step
    op.add_column(
        "workflow_steps",
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "workflow_steps",
        sa.Column("retry_delay_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "step_runs",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
    )

    # Dead man's switch per workflow
    op.add_column(
        "workflows",
        sa.Column("expect_success_within_seconds", sa.Integer(), nullable=True),
    )

    # Outbound alert channels + fired-alert history (also provides cooldown)
    op.create_table(
        "alert_channels",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),  # webhook|discord|telegram
        sa.Column("config", sa.String(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "rules", sa.String(), nullable=False, server_default="{}"
        ),  # JSON: {rule_name: {enabled, params...}}
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "alert_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("rule", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=True),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_alert_events_rule_subject_time",
        "alert_events",
        ["rule", "subject", "fired_at"],
    )

    # Daily exception rollup: outlives celery_events retention
    op.create_table(
        "exception_rollup",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("task_name", sa.String(), nullable=False),
        sa.Column("signature", sa.String(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sample_task_id", sa.String(), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("day", "task_name", "signature"),
    )


def downgrade() -> None:
    op.drop_table("exception_rollup")
    op.drop_index("idx_alert_events_rule_subject_time", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_table("alert_channels")
    op.drop_column("workflows", "expect_success_within_seconds")
    op.drop_column("step_runs", "attempt")
    op.drop_column("workflow_steps", "retry_delay_seconds")
    op.drop_column("workflow_steps", "max_retries")
