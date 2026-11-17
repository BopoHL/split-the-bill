"""what analytics needs: places, what each receipt line is, when a seat paid

Revision ID: 7f8091a2b3c4
Revises: 6e7f8091a2b3
Create Date: 2026-10-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7f8091a2b3c4'
down_revision: Union[str, Sequence[str], None] = '6e7f8091a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'places',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('name_key', sa.String(length=80), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_places_name_key', 'places', ['name_key'], unique=True)

    op.add_column('bills', sa.Column('place_id', sa.Integer(), nullable=True))
    op.add_column('bills', sa.Column('place_checked_at', sa.DateTime(), nullable=True))
    op.create_foreign_key('fk_bills_place_id', 'bills', 'places', ['place_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_bills_place_id', 'bills', ['place_id'])

    op.add_column('bills_users', sa.Column('paid_at', sa.DateTime(), nullable=True))

    op.create_table(
        'dish_kinds',
        sa.Column('key', sa.String(length=40), nullable=False),
        sa.Column('ru', sa.String(length=60), nullable=False),
        sa.Column('uz', sa.String(length=60), nullable=False),
        sa.Column('en', sa.String(length=60), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    op.create_table(
        'dish_labels',
        sa.Column('name_key', sa.String(length=200), nullable=False),
        sa.Column('group', sa.String(), nullable=False, server_default='other'),
        sa.Column('kind', sa.String(length=40), nullable=True),
        sa.Column('model', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('name_key'),
    )


def downgrade() -> None:
    op.drop_table('dish_labels')
    op.drop_table('dish_kinds')
    op.drop_column('bills_users', 'paid_at')
    op.drop_index('ix_bills_place_id', table_name='bills')
    op.drop_constraint('fk_bills_place_id', 'bills', type_='foreignkey')
    op.drop_column('bills', 'place_checked_at')
    op.drop_column('bills', 'place_id')
    op.drop_index('ix_places_name_key', table_name='places')
    op.drop_table('places')
