"""link bill items and files to their receipt task

An item now records WHICH scan produced it (bill_items.receipt_task_id, NULL for
manual items) and a stored scan file points at the same task. The legacy
bill_items.source column remains for one expand/contract release so an old worker
and the new application can safely overlap during deployment.

Revision ID: a9b0c1d2e3f4
Revises: a8b9c0d1e2f3
Create Date: 2026-07-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9b0c1d2e3f4'
down_revision: Union[str, Sequence[str], None] = 'a8b9c0d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Map each item/file to the LATEST scan task of its bill — the one whose items
# are the current ones after any re-scans.
_LATEST_TASK = (
    "(SELECT rt.id FROM receipt_tasks rt "
    "WHERE rt.bill_id = {table}.bill_id ORDER BY rt.id DESC LIMIT 1)"
)


def upgrade() -> None:
    op.create_index(
        'ix_receipt_tasks_bill_id_id', 'receipt_tasks', ['bill_id', 'id'], unique=False
    )

    with op.batch_alter_table('bill_items') as batch_op:
        batch_op.add_column(
            sa.Column('receipt_task_id', sa.Integer(), sa.ForeignKey('receipt_tasks.id'), nullable=True)
        )
        batch_op.create_index('ix_bill_items_receipt_task_id', ['receipt_task_id'])

    with op.batch_alter_table('file_assets') as batch_op:
        batch_op.add_column(
            sa.Column('receipt_task_id', sa.Integer(), sa.ForeignKey('receipt_tasks.id'), nullable=True)
        )
        batch_op.create_index('ix_file_assets_receipt_task_id', ['receipt_task_id'])

    # Existing AI items predate task-scoped provenance, so the latest task is the
    # best available match. New writes populate both fields during the rollout.
    op.execute(
        f"UPDATE bill_items SET receipt_task_id = {_LATEST_TASK.format(table='bill_items')} "
        "WHERE source = 'ai'"
    )

    # A bill may also contain manually attached photos and several historical
    # scans. Match a file to the task whose generated filename is the suffix of
    # its storage path; leave ambiguous/manual assets unlinked.
    matching_task = (
        "(SELECT rt.id FROM receipt_tasks rt "
        "WHERE rt.bill_id = file_assets.bill_id "
        "AND rt.filename IS NOT NULL "
        "AND file_assets.path LIKE ('%/' || rt.filename) "
        "ORDER BY rt.id DESC LIMIT 1)"
    )
    op.execute(
        f"UPDATE file_assets SET receipt_task_id = {matching_task} "
        f"WHERE bill_id IS NOT NULL AND {matching_task} IS NOT NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table('file_assets') as batch_op:
        batch_op.drop_index('ix_file_assets_receipt_task_id')
        batch_op.drop_column('receipt_task_id')
    with op.batch_alter_table('bill_items') as batch_op:
        batch_op.drop_index('ix_bill_items_receipt_task_id')
        batch_op.drop_column('receipt_task_id')
    op.drop_index('ix_receipt_tasks_bill_id_id', table_name='receipt_tasks')
