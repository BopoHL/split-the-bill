"""add unallocated_sum to bills table

Revision ID: 7253c9b0e68e
Revises: 7eb4bf5fedda
Create Date: 2026-02-03 08:30:32.612296

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7253c9b0e68e'
down_revision: Union[str, Sequence[str], None] = '7eb4bf5fedda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('bills')]
    
    if 'unallocated_sum' not in columns:
        op.add_column('bills', sa.Column('unallocated_sum', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('bills')]
    
    if 'unallocated_sum' in columns:
        op.drop_column('bills', 'unallocated_sum')
