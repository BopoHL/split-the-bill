"""add currency to bills

Revision ID: a2b3c4d5e6f7
Revises: a1f2b3c4d5e6
Create Date: 2026-06-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'a1f2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Currency is bound to the bill at creation. server_default backfills
    # existing rows with 'uzs' and matches the model's NOT NULL column.
    op.add_column(
        'bills',
        sa.Column('currency', sa.String(), nullable=False, server_default='uzs'),
    )


def downgrade() -> None:
    op.drop_column('bills', 'currency')
