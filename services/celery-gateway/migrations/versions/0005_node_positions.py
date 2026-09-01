"""node positions

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_nodes", sa.Column("position_x", sa.Float(), nullable=True))
    op.add_column("workflow_nodes", sa.Column("position_y", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("workflow_nodes", "position_y")
    op.drop_column("workflow_nodes", "position_x")
