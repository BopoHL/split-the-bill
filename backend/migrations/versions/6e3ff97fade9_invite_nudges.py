"""When the bot handed a bill's owner the invite, nobody having joined yet.

Revision ID: 6e3ff97fade9
Revises: 0b6bde95cf42
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "6e3ff97fade9"
down_revision: Union[str, Sequence[str], None] = "0b6bde95cf42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("invite_nudged_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("bills", "invite_nudged_at")
