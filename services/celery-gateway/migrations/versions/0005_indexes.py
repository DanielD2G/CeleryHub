"""hot-path indexes for workflow_runs and alert_events

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-01
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # get_workflow_runs / run-durations / comparison all do
    # WHERE workflow_id = ? ORDER BY started_at DESC LIMIT n
    op.create_index(
        "idx_workflow_runs_wf_started",
        "workflow_runs",
        ["workflow_id", "started_at"],
    )
    # GET /api/alerts/events does ORDER BY fired_at DESC LIMIT n with no
    # rule predicate; the existing composite index can't serve that.
    op.create_index("idx_alert_events_fired_at", "alert_events", ["fired_at"])


def downgrade() -> None:
    op.drop_index("idx_alert_events_fired_at", table_name="alert_events")
    op.drop_index("idx_workflow_runs_wf_started", table_name="workflow_runs")
