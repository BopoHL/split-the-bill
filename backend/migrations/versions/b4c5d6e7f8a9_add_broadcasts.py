"""broadcasts and their per-recipient deliveries

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, Sequence[str], None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'broadcasts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('body', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('button_text', sa.String(), nullable=True),
        sa.Column('button_url', sa.String(), nullable=True),
        sa.Column('audience', sa.String(), nullable=False, server_default='all'),
        sa.Column('status', sa.String(), nullable=False, server_default='draft'),
        sa.Column('total_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sent_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_broadcasts_status', 'broadcasts', ['status'])

    op.create_table(
        'broadcast_deliveries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('broadcast_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('error', sa.String(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['broadcast_id'], ['broadcasts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_broadcast_deliveries_broadcast_id', 'broadcast_deliveries', ['broadcast_id'])
    op.create_index('ix_broadcast_deliveries_user_id', 'broadcast_deliveries', ['user_id'])
    op.create_index('ix_broadcast_deliveries_status', 'broadcast_deliveries', ['status'])
    # The sender resumes by skipping what is already recorded, so a repeat run
    # after a restart cannot message anyone twice.
    op.create_index(
        'ix_broadcast_delivery_unique', 'broadcast_deliveries',
        ['broadcast_id', 'user_id'], unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_broadcast_delivery_unique', table_name='broadcast_deliveries')
    op.drop_index('ix_broadcast_deliveries_status', table_name='broadcast_deliveries')
    op.drop_index('ix_broadcast_deliveries_user_id', table_name='broadcast_deliveries')
    op.drop_index('ix_broadcast_deliveries_broadcast_id', table_name='broadcast_deliveries')
    op.drop_table('broadcast_deliveries')
    op.drop_index('ix_broadcasts_status', table_name='broadcasts')
    op.drop_table('broadcasts')
