"""add bot_dialogs table

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-08-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bot_dialogs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('step', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            'draft',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column('prompt_message_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_bot_dialogs_chat_id'), 'bot_dialogs', ['chat_id'], unique=True)
    op.create_index(op.f('ix_bot_dialogs_user_id'), 'bot_dialogs', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_bot_dialogs_user_id'), table_name='bot_dialogs')
    op.drop_index(op.f('ix_bot_dialogs_chat_id'), table_name='bot_dialogs')
    op.drop_table('bot_dialogs')
