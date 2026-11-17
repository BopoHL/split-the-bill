"""A personal invite to a seat no longer keeps the seat from being removed.

Lowering the headcount past a seat someone had been invited to failed with a
foreign-key error, so the table could never shrink.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-11-04
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK = "invites_seat_participant_id_fkey"


def upgrade() -> None:
    op.drop_constraint(FK, "invites", type_="foreignkey")
    op.create_foreign_key(FK, "invites", "bills_users", ["seat_participant_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint(FK, "invites", type_="foreignkey")
    op.create_foreign_key(FK, "invites", "bills_users", ["seat_participant_id"], ["id"])
