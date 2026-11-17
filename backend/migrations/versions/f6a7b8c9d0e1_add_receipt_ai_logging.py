"""add receipt ai logging + scan rating

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('receipt_tasks', sa.Column('ocr_text', sa.Text(), nullable=True))
    op.add_column('receipt_tasks', sa.Column('llm_response', sa.Text(), nullable=True))
    op.add_column('receipt_tasks', sa.Column('scan_quality', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('receipt_tasks', 'scan_quality')
    op.drop_column('receipt_tasks', 'llm_response')
    op.drop_column('receipt_tasks', 'ocr_text')
