"""celery_events partitioned table

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-19
"""
from alembic import op

from celery_gateway.db.events_ddl import CELERY_EVENTS_STATEMENTS, DROP_CELERY_EVENTS

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in CELERY_EVENTS_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(DROP_CELERY_EVENTS)
