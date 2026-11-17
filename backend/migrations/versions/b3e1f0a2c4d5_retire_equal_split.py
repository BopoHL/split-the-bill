"""Bills split «equally» become manual ones.

The app stopped offering an equal split in August and the code that re-divided
such bills whenever someone joined is gone. Their amounts stay exactly as they
are; only a later join no longer re-divides them.

Revision ID: b3e1f0a2c4d5
Revises: af3ba673a960
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b3e1f0a2c4d5"
down_revision: Union[str, Sequence[str], None] = "af3ba673a960"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE bills SET split_type = 'manual' WHERE split_type = 'equally'")


def downgrade() -> None:
    # Which bills were split equally is not kept, and manual is a valid split
    # for every one of them, so there is nothing to put back.
    pass
