"""A bill's place as its owner said it: a later scan leaves it alone.

Revision ID: e5bd630db327
Revises: 91a2b3c4d5e6
Create Date: 2026-10-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5bd630db327"
down_revision: Union[str, Sequence[str], None] = "91a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("place_by_owner", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("bills", "place_by_owner")
