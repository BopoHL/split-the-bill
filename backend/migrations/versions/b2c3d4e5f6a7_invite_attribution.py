"""invite attribution: who brought whom, and through which channel

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-19

A bill's public_token is one value per bill, shared by everyone at the table,
so it cannot say who did the sharing. Invites are minted per share instead, and
the two backfilled columns record the answer where it is read: once per account
(first touch) and once per seat.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'invites',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('bill_id', sa.Integer(), sa.ForeignKey('bills.id'), nullable=False),
        sa.Column(
            'inviter_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False
        ),
        sa.Column(
            'seat_participant_id',
            sa.Integer(),
            sa.ForeignKey('bills_users.id'),
            nullable=True,
        ),
        sa.Column('channel', sa.String(), nullable=False, server_default='link'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_invites_code', 'invites', ['code'], unique=True)
    op.create_index('ix_invites_bill_id', 'invites', ['bill_id'])
    op.create_index('ix_invites_inviter_user_id', 'invites', ['inviter_user_id'])

    op.add_column('users', sa.Column('invited_by_user_id', sa.Integer(), nullable=True))
    op.create_index('ix_users_invited_by_user_id', 'users', ['invited_by_user_id'])
    op.create_foreign_key(
        'fk_users_invited_by_user_id', 'users', 'users', ['invited_by_user_id'], ['id']
    )

    op.add_column(
        'bills_users', sa.Column('invited_by_user_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_bills_users_invited_by_user_id',
        'bills_users',
        'users',
        ['invited_by_user_id'],
        ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_bills_users_invited_by_user_id', 'bills_users', type_='foreignkey')
    op.drop_column('bills_users', 'invited_by_user_id')
    op.drop_constraint('fk_users_invited_by_user_id', 'users', type_='foreignkey')
    op.drop_index('ix_users_invited_by_user_id', table_name='users')
    op.drop_column('users', 'invited_by_user_id')
    op.drop_index('ix_invites_inviter_user_id', table_name='invites')
    op.drop_index('ix_invites_bill_id', table_name='invites')
    op.drop_index('ix_invites_code', table_name='invites')
    op.drop_table('invites')
