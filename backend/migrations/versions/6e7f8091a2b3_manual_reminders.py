"""reminders an owner sends by hand, and how each one went

Revision ID: 6e7f8091a2b3
Revises: 5d6e7f8091a2
Create Date: 2026-10-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6e7f8091a2b3'
down_revision: Union[str, Sequence[str], None] = '5d6e7f8091a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'manual_reminders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bill_id', sa.Integer(), nullable=False),
        sa.Column('participant_id', sa.Integer(), nullable=False),
        sa.Column('requested_by_user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('channel', sa.String(), nullable=True),
        sa.Column('sender_account_id', sa.Integer(), nullable=True),
        sa.Column('failure', sa.String(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['bill_id'], ['bills.id']),
        sa.ForeignKeyConstraint(['participant_id'], ['bills_users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['sender_account_id'], ['sender_accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_manual_reminders_bill_id', 'manual_reminders', ['bill_id'])
    op.create_index('ix_manual_reminders_participant_id', 'manual_reminders', ['participant_id'])
    # The delivery job picks up whatever is still pending.
    op.create_index('ix_manual_reminders_status', 'manual_reminders', ['status'])


def downgrade() -> None:
    op.drop_index('ix_manual_reminders_status', table_name='manual_reminders')
    op.drop_index('ix_manual_reminders_participant_id', table_name='manual_reminders')
    op.drop_index('ix_manual_reminders_bill_id', table_name='manual_reminders')
    op.drop_table('manual_reminders')
