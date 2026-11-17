"""targeted broadcasts and an explicit parse mode

Revision ID: e7f8a9b0c1d2
Revises: c5d6e7f8a9b0
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, Sequence[str], None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Recipients are resolved when the broadcast is created, not when it is
    # sent, so a username changing in between can't redirect a message.
    op.add_column(
        'broadcasts',
        sa.Column(
            'target_user_ids',
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        'broadcasts',
        sa.Column('parse_mode', sa.String(), nullable=True, server_default='HTML'),
    )


def downgrade() -> None:
    op.drop_column('broadcasts', 'parse_mode')
    op.drop_column('broadcasts', 'target_user_ids')
