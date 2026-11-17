"""drop expected_people/payment_details from receipt_tasks

The bill is now created up front (it owns headcount/payment/currency) and the
worker only enriches it, so these transit columns on the task are no longer used.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-06-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table so the drop also works on SQLite (table recreate).
    with op.batch_alter_table('receipt_tasks') as batch_op:
        batch_op.drop_column('payment_details')
        batch_op.drop_column('expected_people')


def downgrade() -> None:
    with op.batch_alter_table('receipt_tasks') as batch_op:
        batch_op.add_column(sa.Column('expected_people', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('payment_details', sa.String(), nullable=True))
