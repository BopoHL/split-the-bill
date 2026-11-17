"""add expected_people to bills + scan-carried meta to receipt_tasks

Revision ID: a1f2b3c4d5e6
Revises: f7b8c9d0e1f2
Create Date: 2026-06-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'f7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bills', sa.Column('expected_people', sa.Integer(), nullable=True))
    op.add_column('receipt_tasks', sa.Column('expected_people', sa.Integer(), nullable=True))
    op.add_column('receipt_tasks', sa.Column('payment_details', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('receipt_tasks', 'payment_details')
    op.drop_column('receipt_tasks', 'expected_people')
    op.drop_column('bills', 'expected_people')
