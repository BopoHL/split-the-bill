"""add bill_items.source

Records how each item was created — 'manual' (by hand) or 'ai' (scan worker) —
so a re-scan replaces only the AI items and keeps manual ones (STB-207). A
string column (rather than a bool) leaves room for future sources.

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-06-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('bill_items') as batch_op:
        batch_op.add_column(
            sa.Column('source', sa.String(), nullable=False, server_default='manual')
        )


def downgrade() -> None:
    with op.batch_alter_table('bill_items') as batch_op:
        batch_op.drop_column('source')
