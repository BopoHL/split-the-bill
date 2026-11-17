"""bills made by the guided tour are marked as demo

Revision ID: 3b4c5d6e7f80
Revises: 2ad865f109e2
Create Date: 2026-09-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3b4c5d6e7f80'
down_revision: Union[str, Sequence[str], None] = '2ad865f109e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'bills',
        sa.Column('is_demo', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('bills', 'is_demo')
