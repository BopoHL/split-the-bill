"""replace_is_closed_with_status

Revision ID: 9385b2c2c011
Revises: cb0d734b954b
Create Date: 2026-02-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9385b2c2c011'
down_revision: Union[str, Sequence[str], None] = 'cb0d734b954b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('bills', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(), server_default='open', nullable=False))
        batch_op.drop_column('is_closed')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('bills', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_closed', sa.Boolean(), server_default=sa.text('false'), nullable=False))
        batch_op.drop_column('status')
