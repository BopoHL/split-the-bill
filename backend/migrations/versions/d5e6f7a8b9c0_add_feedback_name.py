"""add optional name to feedback

Lets a submitter optionally sign their feedback with a display name (STB-189);
nullable so existing rows and anonymous submissions are unaffected.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table so the add also works on SQLite (table recreate).
    with op.batch_alter_table('feedback') as batch_op:
        batch_op.add_column(sa.Column('name', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('feedback') as batch_op:
        batch_op.drop_column('name')
