"""«Remind everyone» pressed without Pro, counted against the month's free ones.

Revision ID: e2f3a4b5c6d7
Revises: d31e6dcc9615
Create Date: 2026-11-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d31e6dcc9615"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "free_reminder_uses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_free_reminder_uses_user_id", "free_reminder_uses", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_free_reminder_uses_user_id", table_name="free_reminder_uses")
    op.drop_table("free_reminder_uses")
