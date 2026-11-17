"""per-portion item assignments: add portion_index to bill_item_assignments

A bill item with count N now has portions 0..N-1, each shareable independently.
Existing assignments were item-level (shared across the whole item), so to keep
their split unchanged we replicate each existing assignment across all portions
of multi-quantity items (single-quantity items already map to portion 0).

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-06-20

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, Sequence[str], None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'bill_item_assignments',
        sa.Column('portion_index', sa.Integer(), nullable=False, server_default='0'),
    )
    # Drop the old (item,user) uniqueness so a user can hold several portions of
    # one item before the new (item,portion,user) index is created.
    op.drop_index('ix_item_user_unique', table_name='bill_item_assignments')

    # Preserve old whole-item sharing: replicate each existing assignment across
    # the remaining portions of multi-quantity items.
    conn = op.get_bind()
    now = datetime.utcnow()
    rows = conn.execute(sa.text(
        "SELECT a.bill_item_id AS item_id, a.user_id AS user_id, i.count AS cnt "
        "FROM bill_item_assignments a "
        "JOIN bill_items i ON i.id = a.bill_item_id "
        "WHERE i.count > 1"
    )).fetchall()
    for row in rows:
        for portion in range(1, int(row.cnt)):
            conn.execute(
                sa.text(
                    "INSERT INTO bill_item_assignments "
                    "(bill_item_id, user_id, portion_index, created_at, updated_at) "
                    "VALUES (:item, :user, :portion, :now, :now)"
                ),
                {"item": row.item_id, "user": row.user_id, "portion": portion, "now": now},
            )

    op.create_index(
        'ix_item_portion_user_unique',
        'bill_item_assignments',
        ['bill_item_id', 'portion_index', 'user_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_item_portion_user_unique', table_name='bill_item_assignments')
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM bill_item_assignments WHERE portion_index > 0"))
    op.create_index(
        'ix_item_user_unique',
        'bill_item_assignments',
        ['bill_item_id', 'user_id'],
        unique=True,
    )
    op.drop_column('bill_item_assignments', 'portion_index')
