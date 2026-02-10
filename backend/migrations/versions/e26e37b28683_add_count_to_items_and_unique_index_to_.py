"""Add count to items and unique index to bill_user

Revision ID: e26e37b28683
Revises: 
Create Date: 2026-02-02 10:41:21.906797

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e26e37b28683'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # Check if 'count' column already exists in 'bill_items'
    columns = [c['name'] for c in inspector.get_columns('bill_items')]
    if 'count' not in columns:
        op.add_column('bill_items', sa.Column('count', sa.Integer(), nullable=False, server_default='1'))
    
    # Check if index exists before dropping
    indexes = [i['name'] for i in inspector.get_indexes('bills_users')]
    if 'ix_bills_users_bill_id' in indexes:
        op.drop_index('ix_bills_users_bill_id', table_name='bills_users')
    
    # Check if unique index exists before creating
    if 'ix_bill_user_unique' not in indexes:
        op.create_index('ix_bill_user_unique', 'bills_users', ['bill_id', 'user_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    indexes = [i['name'] for i in inspector.get_indexes('bills_users')]
    
    if 'ix_bill_user_unique' in indexes:
        op.drop_index('ix_bill_user_unique', table_name='bills_users')
    
    if 'ix_bills_users_bill_id' not in indexes:
        op.create_index('ix_bills_users_bill_id', 'bills_users', ['bill_id'], unique=False)
        
    columns = [c['name'] for c in inspector.get_columns('bill_items')]
    if 'count' in columns:
        op.drop_column('bill_items', 'count')
