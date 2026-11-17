"""scheduled broadcasts

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-08-14

Stored in UTC, like every other timestamp here, so the host's timezone is
irrelevant. The operator picks a Tashkent wall-clock time and the admin panel
converts it once, at the edge.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f8a9b0c1d2e3'
down_revision: Union[str, Sequence[str], None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('broadcasts', sa.Column('scheduled_at', sa.DateTime(), nullable=True))
    op.create_index('ix_broadcasts_scheduled_at', 'broadcasts', ['scheduled_at'])


def downgrade() -> None:
    op.drop_index('ix_broadcasts_scheduled_at', table_name='broadcasts')
    op.drop_column('broadcasts', 'scheduled_at')
