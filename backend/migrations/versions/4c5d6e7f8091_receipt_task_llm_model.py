"""scans remember which model read them

Revision ID: 4c5d6e7f8091
Revises: 3b4c5d6e7f80
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4c5d6e7f8091'
down_revision: Union[str, Sequence[str], None] = '3b4c5d6e7f80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('receipt_tasks', sa.Column('llm_model', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('receipt_tasks', 'llm_model')
