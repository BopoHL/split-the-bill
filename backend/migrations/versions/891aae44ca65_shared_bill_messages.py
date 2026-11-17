"""shared bill messages: the chat posts kept current as a bill changes

Revision ID: 891aae44ca65
Revises: e4f5a6b7c8d9
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '891aae44ca65'
down_revision: Union[str, Sequence[str], None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'shared_bill_messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('bill_id', sa.Integer(), sa.ForeignKey('bills.id'), nullable=False),
        sa.Column('invite_code', sa.String(), nullable=False),
        sa.Column('language', sa.String(), nullable=False),
        sa.Column('inline_message_id', sa.String(), nullable=True),
        sa.Column('fingerprint', sa.String(), nullable=True),
        sa.Column('refreshed_at', sa.DateTime(), nullable=True),
        sa.Column('is_final', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_gone', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_shared_bill_messages_bill_id', 'shared_bill_messages', ['bill_id'])
    op.create_index('ix_shared_bill_messages_invite_code', 'shared_bill_messages', ['invite_code'])
    op.create_index(
        'ix_shared_bill_messages_inline_message_id',
        'shared_bill_messages',
        ['inline_message_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_shared_bill_messages_inline_message_id', table_name='shared_bill_messages')
    op.drop_index('ix_shared_bill_messages_invite_code', table_name='shared_bill_messages')
    op.drop_index('ix_shared_bill_messages_bill_id', table_name='shared_bill_messages')
    op.drop_table('shared_bill_messages')
