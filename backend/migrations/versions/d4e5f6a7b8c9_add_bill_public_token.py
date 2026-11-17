"""add bill public_token

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-01

"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add the column nullable so existing rows can be backfilled.
    op.add_column(
        'bills',
        sa.Column('public_token', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )

    # 2. Backfill existing bills with unique random tokens.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id FROM bills WHERE public_token IS NULL")
    ).fetchall()
    for (bill_id,) in rows:
        conn.execute(
            sa.text("UPDATE bills SET public_token = :tok WHERE id = :id"),
            {"tok": secrets.token_urlsafe(12), "id": bill_id},
        )

    # 3. Enforce NOT NULL + a unique index.
    op.alter_column('bills', 'public_token', nullable=False)
    op.create_index(
        op.f('ix_bills_public_token'), 'bills', ['public_token'], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_bills_public_token'), table_name='bills')
    op.drop_column('bills', 'public_token')
