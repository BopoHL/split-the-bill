"""When a bill's owner learned that a seat was paid.

Revision ID: d31e6dcc9615
Revises: 6e3ff97fade9
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d31e6dcc9615"
down_revision: Union[str, Sequence[str], None] = "6e3ff97fade9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bills_users", sa.Column("owner_told_at", sa.DateTime(), nullable=True))
    # Payments made before the bot told owners of them are old news.
    op.execute("UPDATE bills_users SET owner_told_at = paid_at WHERE is_paid")


def downgrade() -> None:
    op.drop_column("bills_users", "owner_told_at")
