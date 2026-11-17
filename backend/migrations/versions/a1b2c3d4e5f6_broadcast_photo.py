"""a photo on a broadcast

Revision ID: a1b2c3d4e5f6
Revises: f8a9b0c1d2e3
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('broadcasts', sa.Column('photo_path', sa.String(), nullable=True))
    op.add_column('broadcasts', sa.Column('photo_file_id', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('broadcasts', 'photo_file_id')
    op.drop_column('broadcasts', 'photo_path')
