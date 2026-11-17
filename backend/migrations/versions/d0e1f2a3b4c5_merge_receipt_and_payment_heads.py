"""merge receipt provenance and payment index heads

Revision ID: d0e1f2a3b4c5
Revises: a9b0c1d2e3f4, c9d0e1f2a3b4
Create Date: 2026-07-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op


revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, Sequence[str], None] = (
    'a9b0c1d2e3f4',
    'c9d0e1f2a3b4',
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Some non-production environments may already have executed an earlier
    # copy of a9b0c1d2e3f4 that dropped source. Repair those schemas while fresh
    # installs keep the column created by a8b9c0d1e2f3.
    if not context.is_offline_mode():
        columns = {
            column['name']
            for column in sa.inspect(op.get_bind()).get_columns('bill_items')
        }
        if 'source' not in columns:
            with op.batch_alter_table('bill_items') as batch_op:
                batch_op.add_column(
                    sa.Column(
                        'source', sa.String(), nullable=False, server_default='manual'
                    )
                )
    op.execute("UPDATE bill_items SET source = 'ai' WHERE receipt_task_id IS NOT NULL")


def downgrade() -> None:
    pass
