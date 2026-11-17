"""accounts that deliver reminders the bot cannot

Revision ID: 5d6e7f8091a2
Revises: 4c5d6e7f8091
Create Date: 2026-10-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5d6e7f8091a2'
down_revision: Union[str, Sequence[str], None] = '4c5d6e7f8091'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sender_accounts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('phone', sa.String(), nullable=False),
        sa.Column('session_enc', sa.String(), nullable=True),
        sa.Column('phone_code_hash', sa.String(), nullable=True),
        sa.Column('telegram_id', sa.BigInteger(), nullable=True),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('display_name', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='awaiting_code'),
        sa.Column('rest_until', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.String(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('sent_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_sender_accounts_phone', 'sender_accounts', ['phone'], unique=True)
    op.create_index('ix_sender_accounts_status', 'sender_accounts', ['status'])


def downgrade() -> None:
    op.drop_index('ix_sender_accounts_status', table_name='sender_accounts')
    op.drop_index('ix_sender_accounts_phone', table_name='sender_accounts')
    op.drop_table('sender_accounts')
