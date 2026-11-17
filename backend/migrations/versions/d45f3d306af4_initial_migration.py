"""Initial migration

Revision ID: d45f3d306af4
Revises:
Create Date: 2026-02-14 13:31:51.253732

NOTE (backfilled 2026-05-31): this migration was originally empty
because schemas had been created via SQLModel.metadata.create_all and
autogenerate ran against an already-populated database. Later
migrations assume these tables exist, so `alembic upgrade head` on a
fresh database used to fail. The CREATE TABLEs below describe the
schema as it stood BEFORE 664900246755 (name/surname) and 03f6caf32603
(split_by_items).

Existing environments (prod) already have this revision stamped in
alembic_version, so this code will NOT re-run there — it only affects
fresh databases.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd45f3d306af4'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # users
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('avatar_url', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_telegram_id', 'users', ['telegram_id'], unique=True)

    # bills
    op.create_table(
        'bills',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('total_sum', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('unallocated_sum', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('payment_details', sa.String(), nullable=True),
        sa.Column('split_type', sa.String(), nullable=False, server_default='manual'),
        sa.Column('status', sa.String(), nullable=False, server_default='open'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # bill_items (initial layout: has assigned_to_user_id, no is_shared_globally;
    # the later migration 03f6caf32603 drops the FK column and adds the flag)
    op.create_table(
        'bill_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bill_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('price', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('item_sum', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('assigned_to_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['bill_id'], ['bills.id']),
        sa.ForeignKeyConstraint(['assigned_to_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_bill_items_bill_id', 'bill_items', ['bill_id'], unique=False)

    # bills_users
    op.create_table(
        'bills_users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bill_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('guest_name', sa.String(), nullable=True),
        sa.Column('allocated_amount', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('is_paid', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['bill_id'], ['bills.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_bills_users_user_id', 'bills_users', ['user_id'], unique=False)
    op.create_index('ix_bill_user_unique', 'bills_users', ['bill_id', 'user_id'], unique=True)

    # receipt_tasks
    op.create_table(
        'receipt_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('bill_id', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['bill_id'], ['bills.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_receipt_tasks_user_id', 'receipt_tasks', ['user_id'], unique=False)
    op.create_index('ix_receipt_tasks_status', 'receipt_tasks', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_receipt_tasks_status', table_name='receipt_tasks')
    op.drop_index('ix_receipt_tasks_user_id', table_name='receipt_tasks')
    op.drop_table('receipt_tasks')

    op.drop_index('ix_bill_user_unique', table_name='bills_users')
    op.drop_index('ix_bills_users_user_id', table_name='bills_users')
    op.drop_table('bills_users')

    op.drop_index('ix_bill_items_bill_id', table_name='bill_items')
    op.drop_table('bill_items')

    op.drop_table('bills')

    op.drop_index('ix_users_telegram_id', table_name='users')
    op.drop_table('users')
