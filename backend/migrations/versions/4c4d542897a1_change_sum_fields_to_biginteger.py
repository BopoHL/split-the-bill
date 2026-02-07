"""change sum fields to BigInteger

Revision ID: 4c4d542897a1
Revises: 7253c9b0e68e
Create Date: 2026-02-03 08:36:40.999076

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c4d542897a1'
down_revision: Union[str, Sequence[str], None] = '7253c9b0e68e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite does not support ALTER COLUMN TYPE.
    # Since SQLite's INTEGER is already 64-bit, no action is required here.
    # This migration exists to keep the code's use of BigInteger in sync with the DB versioning.
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
