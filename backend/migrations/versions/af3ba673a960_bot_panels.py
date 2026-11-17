"""The bot keeps one message per chat to redraw instead of sending new ones.

bot_dialogs.prompt_message_id goes out of use with it, but stays until the
release after: the code still running while this migrates reads it.

Revision ID: af3ba673a960
Revises: 315125518753
Create Date: 2026-10-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "af3ba673a960"
down_revision: Union[str, Sequence[str], None] = "315125518753"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bot_panels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("bottom_message_id", sa.Integer(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bot_panels_chat_id"), "bot_panels", ["chat_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_bot_panels_chat_id"), table_name="bot_panels")
    op.drop_table("bot_panels")
