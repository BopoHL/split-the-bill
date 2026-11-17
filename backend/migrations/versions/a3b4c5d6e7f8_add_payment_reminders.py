"""payment reminders

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, Sequence[str], None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payment_reminders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bill_id', sa.Integer(), nullable=False),
        sa.Column('participant_id', sa.Integer(), nullable=False),
        sa.Column('sent_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_sent_at', sa.DateTime(), nullable=True),
        sa.Column('next_due_at', sa.DateTime(), nullable=True),
        sa.Column('muted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['bill_id'], ['bills.id']),
        sa.ForeignKeyConstraint(['participant_id'], ['bills_users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_payment_reminders_bill_id', 'payment_reminders', ['bill_id'])
    op.create_index('ix_payment_reminders_participant_id', 'payment_reminders', ['participant_id'])
    op.create_index(
        'ix_payment_reminder_unique', 'payment_reminders',
        ['bill_id', 'participant_id'], unique=True,
    )
    # The tick selects "everything due now", so this is the only index it needs.
    op.create_index('ix_payment_reminder_due', 'payment_reminders', ['next_due_at'])


def downgrade() -> None:
    op.drop_index('ix_payment_reminder_due', table_name='payment_reminders')
    op.drop_index('ix_payment_reminder_unique', table_name='payment_reminders')
    op.drop_index('ix_payment_reminders_participant_id', table_name='payment_reminders')
    op.drop_index('ix_payment_reminders_bill_id', table_name='payment_reminders')
    op.drop_table('payment_reminders')
