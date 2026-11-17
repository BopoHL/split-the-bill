"""hide saved cards instead of deleting them

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-08-12

Bills reference payment_methods, so removing a card the user had ever used
failed on the foreign key — which is why «delete» silently did nothing. Nulling
the reference instead would strip the card off past bills, so the row stays and
only disappears from the picker.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, Sequence[str], None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payment_methods', sa.Column('deleted_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('payment_methods', 'deleted_at')
