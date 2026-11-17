"""A broadcast can go out as a rich message: pictures inside the text.

Revision ID: 315125518753
Revises: aa97ebdfdc5a
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "315125518753"
down_revision: Union[str, Sequence[str], None] = "aa97ebdfdc5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "broadcasts",
        sa.Column("format", sa.String(), nullable=False, server_default="message"),
    )


def downgrade() -> None:
    op.drop_column("broadcasts", "format")
