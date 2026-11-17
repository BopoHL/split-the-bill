"""switchable receipt scan modes

Revision ID: d3e4f5a6b7c8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    op.add_column('receipt_tasks', sa.Column('scan_mode', sa.String(), nullable=True))
    op.create_index('ix_receipt_tasks_scan_mode', 'receipt_tasks', ['scan_mode'])


def downgrade() -> None:
    op.drop_index('ix_receipt_tasks_scan_mode', table_name='receipt_tasks')
    op.drop_column('receipt_tasks', 'scan_mode')
    op.drop_table('app_settings')
