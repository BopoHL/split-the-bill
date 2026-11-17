"""seats for ephemeral guests; assignments point at participants

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-11

Two changes that only make sense together.

`bills_users` gains a seat: the owner is seat 0 and the remaining seats are
created up front as unclaimed guests, so dishes can be assigned before anyone
joins.

`bill_item_assignments` then has to stop pointing at `users`. A guest seat has
no account behind it, so an assignment keyed by user_id simply cannot express
"this dish belongs to Guest 2". It now references `bills_users`, which also
makes it impossible to assign an item to someone who isn't in the bill.

NOTE: downgrade is lossy. Assignments belonging to guest seats have no user to
map back to and are dropped.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'bills_users',
        sa.Column('seat_index', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column('bills_users', sa.Column('claimed_at', sa.DateTime(), nullable=True))

    # Existing participants keep their current order; the owner is pulled to
    # seat 0 so the invariant holds for old bills too.
    op.execute(
        """
        UPDATE bills_users AS bu
        SET seat_index = ranked.rn
        FROM (
            SELECT bu2.id,
                   ROW_NUMBER() OVER (
                       PARTITION BY bu2.bill_id
                       ORDER BY (bu2.user_id IS DISTINCT FROM b.owner_id), bu2.id
                   ) - 1 AS rn
            FROM bills_users AS bu2
            JOIN bills AS b ON b.id = bu2.bill_id
        ) AS ranked
        WHERE ranked.id = bu.id
        """
    )
    # Everyone who is already in a bill has an account behind them.
    op.execute("UPDATE bills_users SET claimed_at = created_at WHERE user_id IS NOT NULL")
    op.create_index('ix_bill_user_seat', 'bills_users', ['bill_id', 'seat_index'], unique=True)

    op.add_column(
        'bill_item_assignments', sa.Column('participant_id', sa.Integer(), nullable=True)
    )
    op.execute(
        """
        UPDATE bill_item_assignments AS a
        SET participant_id = bu.id
        FROM bill_items AS i
        JOIN bills_users AS bu ON bu.bill_id = i.bill_id
        WHERE i.id = a.bill_item_id AND bu.user_id = a.user_id
        """
    )
    # Assignments whose participant was removed from the bill are orphans and
    # were already invisible everywhere; drop them rather than fail NOT NULL.
    op.execute("DELETE FROM bill_item_assignments WHERE participant_id IS NULL")

    op.alter_column('bill_item_assignments', 'participant_id', nullable=False)
    op.create_foreign_key(
        'fk_assignment_participant',
        'bill_item_assignments', 'bills_users',
        ['participant_id'], ['id'],
        ondelete='CASCADE',
    )
    op.create_index(
        'ix_bill_item_assignments_participant_id', 'bill_item_assignments', ['participant_id']
    )
    op.drop_index('ix_item_portion_user_unique', table_name='bill_item_assignments')
    op.create_index(
        'ix_item_portion_participant_unique',
        'bill_item_assignments',
        ['bill_item_id', 'portion_index', 'participant_id'],
        unique=True,
    )
    op.drop_column('bill_item_assignments', 'user_id')


def downgrade() -> None:
    op.add_column('bill_item_assignments', sa.Column('user_id', sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE bill_item_assignments AS a
        SET user_id = bu.user_id
        FROM bills_users AS bu
        WHERE bu.id = a.participant_id
        """
    )
    # Guest seats have no account to map back to.
    op.execute("DELETE FROM bill_item_assignments WHERE user_id IS NULL")
    op.alter_column('bill_item_assignments', 'user_id', nullable=False)
    op.create_foreign_key(
        None, 'bill_item_assignments', 'users', ['user_id'], ['id']
    )
    op.drop_index('ix_item_portion_participant_unique', table_name='bill_item_assignments')
    op.create_index(
        'ix_item_portion_user_unique',
        'bill_item_assignments',
        ['bill_item_id', 'portion_index', 'user_id'],
        unique=True,
    )
    op.drop_index('ix_bill_item_assignments_participant_id', table_name='bill_item_assignments')
    op.drop_constraint('fk_assignment_participant', 'bill_item_assignments', type_='foreignkey')
    op.drop_column('bill_item_assignments', 'participant_id')

    op.drop_index('ix_bill_user_seat', table_name='bills_users')
    op.drop_column('bills_users', 'claimed_at')
    op.drop_column('bills_users', 'seat_index')
