"""add receipt source (photo/soliq_qr) + source_url; make filename nullable

Soliq QR imports have no image, so `filename` becomes nullable and the task
records where it came from (`source`) and, for QR, the validated ofd.soliq.uz
check URL the worker fetches (`source_url`).

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-06-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table so the column changes also work on SQLite (table recreate).
    with op.batch_alter_table('receipt_tasks') as batch_op:
        batch_op.add_column(
            sa.Column('source', sa.String(), nullable=False, server_default='photo')
        )
        batch_op.add_column(sa.Column('source_url', sa.String(), nullable=True))
        batch_op.alter_column('filename', existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('receipt_tasks') as batch_op:
        batch_op.alter_column('filename', existing_type=sa.String(), nullable=False)
        batch_op.drop_column('source_url')
        batch_op.drop_column('source')
