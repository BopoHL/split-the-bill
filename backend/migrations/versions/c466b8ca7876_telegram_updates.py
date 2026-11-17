"""Telegram's updates kept until the bot's worker has handled them.

Revision ID: c466b8ca7876
Revises: 93f2fef4c9f3
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c466b8ca7876"
down_revision: Union[str, Sequence[str], None] = "93f2fef4c9f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_updates",
        sa.Column("update_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("lane", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("not_before", sa.DateTime(), nullable=True),
        sa.Column("claimed_until", sa.DateTime(), nullable=True),
        sa.Column("claimed_by", sa.String(length=32), nullable=True),
        sa.Column("done_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("update_id"),
    )
    op.create_index(
        "ix_telegram_updates_waiting", "telegram_updates", ["lane", "update_id"],
        postgresql_where=sa.text("done_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_updates_waiting", table_name="telegram_updates")
    op.drop_table("telegram_updates")
