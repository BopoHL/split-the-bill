"""add file_assets

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'file_assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('bill_id', sa.Integer(), nullable=True),
        sa.Column('original_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('path', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('mime_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='application/octet-stream'),
        sa.Column('storage_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='local'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['bill_id'], ['bills.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_file_assets_user_id'), 'file_assets', ['user_id'], unique=False)
    op.create_index(op.f('ix_file_assets_bill_id'), 'file_assets', ['bill_id'], unique=False)
    op.create_index(op.f('ix_file_assets_path'), 'file_assets', ['path'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_file_assets_path'), table_name='file_assets')
    op.drop_index(op.f('ix_file_assets_bill_id'), table_name='file_assets')
    op.drop_index(op.f('ix_file_assets_user_id'), table_name='file_assets')
    op.drop_table('file_assets')
