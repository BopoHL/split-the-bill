"""tell a chat when its scan is done

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-08-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'receipt_tasks',
        sa.Column('notify_chat_id', sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('receipt_tasks', 'notify_chat_id')
