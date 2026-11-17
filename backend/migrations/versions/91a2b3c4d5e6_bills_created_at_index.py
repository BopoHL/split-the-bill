"""Bills by when they were made: the admin pages through all of them newest
first.

Revision ID: 91a2b3c4d5e6
Revises: 8091a2b3c4d5
Create Date: 2026-10-04
"""
from typing import Sequence, Union

from alembic import op

revision: str = "91a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "8091a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_bills_created_at", "bills", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_bills_created_at", table_name="bills")
