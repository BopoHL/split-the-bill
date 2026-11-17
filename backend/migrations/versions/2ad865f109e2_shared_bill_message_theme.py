"""shared bill messages keep the sharer's theme for their picture

Revision ID: 2ad865f109e2
Revises: 891aae44ca65
Create Date: 2026-09-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2ad865f109e2'
down_revision: Union[str, Sequence[str], None] = '891aae44ca65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'shared_bill_messages',
        sa.Column('theme', sa.String(), nullable=False, server_default='light'),
    )


def downgrade() -> None:
    op.drop_column('shared_bill_messages', 'theme')
