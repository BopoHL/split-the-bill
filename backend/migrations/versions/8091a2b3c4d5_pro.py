"""Pro: the stretches of time people have it for, and promo codes. Everyone
starts on Free: Pro at the launch is given by a promo code, not by this.

Revision ID: 8091a2b3c4d5
Revises: 7f8091a2b3c4
Create Date: 2026-10-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8091a2b3c4d5'
down_revision: Union[str, Sequence[str], None] = '7f8091a2b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'promo_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('days', sa.Integer(), nullable=False),
        sa.Column('max_uses', sa.Integer(), nullable=True),
        sa.Column('uses', sa.Integer(), server_default='0', nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_promo_codes_code', 'promo_codes', ['code'], unique=True)

    op.create_table(
        'pro_grants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('plan', sa.String(length=20), nullable=True),
        sa.Column('starts_at', sa.DateTime(), nullable=False),
        sa.Column('ends_at', sa.DateTime(), nullable=False),
        sa.Column('stars', sa.Integer(), nullable=True),
        sa.Column('charge_id', sa.String(length=255), nullable=True),
        sa.Column('promo_code_id', sa.Integer(), nullable=True),
        sa.Column('ending_noted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['promo_code_id'], ['promo_codes.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('charge_id'),
        sa.UniqueConstraint('user_id', 'promo_code_id', name='uq_pro_grants_user_promo'),
    )
    op.create_index('ix_pro_grants_user_id', 'pro_grants', ['user_id'])
    op.create_index('ix_pro_grants_ends_at', 'pro_grants', ['ends_at'])


def downgrade() -> None:
    op.drop_index('ix_pro_grants_ends_at', table_name='pro_grants')
    op.drop_index('ix_pro_grants_user_id', table_name='pro_grants')
    op.drop_table('pro_grants')
    op.drop_index('ix_promo_codes_code', table_name='promo_codes')
    op.drop_table('promo_codes')
