"""add index on bills.payment_method_id

The model has always declared bills.payment_method_id as index=True, but the
migration that introduced the column (f7a8b9c0d1e2) created only the FK, not the
index — so prod never had ix_bills_payment_method_id and `alembic check` kept
flagging the drift. This adds the missing index (STB-223).

Revision ID: c9d0e1f2a3b4
Revises: a8b9c0d1e2f3
Create Date: 2026-07-02

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'a8b9c0d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f('ix_bills_payment_method_id'), 'bills', ['payment_method_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_bills_payment_method_id'), table_name='bills')
