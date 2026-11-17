"""add_name_surname_to_users

Revision ID: 664900246755
Revises: d45f3d306af4
Create Date: 2026-02-14 19:39:41.873130

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '664900246755'
down_revision: Union[str, Sequence[str], None] = 'd45f3d306af4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('name', sa.String(), nullable=True))
    op.add_column('users', sa.Column('surname', sa.String(), nullable=True))
    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'surname')
    op.drop_column('users', 'name')
    pass
