"""soft delete for bills

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Deleting a bill now only marks it. Items, participants and assignments
    # carry no flag of their own — they are filtered through the bill, so there
    # is no query left where one could be forgotten.
    op.add_column('bills', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    # Every listing is "this user's bills that are not deleted".
    op.create_index('ix_bills_owner_deleted', 'bills', ['owner_id', 'deleted_at'])


def downgrade() -> None:
    op.drop_index('ix_bills_owner_deleted', table_name='bills')
    op.drop_column('bills', 'deleted_at')
