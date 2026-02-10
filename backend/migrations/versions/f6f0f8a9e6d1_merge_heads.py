"""merge heads

Revision ID: f6f0f8a9e6d1
Revises: 2e6f9f1351c7, 9385b2c2c011
Create Date: 2026-02-10 08:14:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6f0f8a9e6d1'
down_revision: Union[str, Sequence[str], None] = ('2e6f9f1351c7', '9385b2c2c011')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
