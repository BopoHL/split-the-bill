"""A payment the bot's worker gave up on, settled by hand from the admin panel.

Revision ID: aa97ebdfdc5a
Revises: c466b8ca7876
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "aa97ebdfdc5a"
down_revision: Union[str, Sequence[str], None] = "c466b8ca7876"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("telegram_updates", sa.Column("settled_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("telegram_updates", "settled_at")
