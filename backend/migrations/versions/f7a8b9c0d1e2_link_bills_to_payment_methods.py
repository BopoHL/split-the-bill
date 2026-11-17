"""link bills to encrypted payment_methods, drop plaintext payment_details

Stops storing card numbers in the clear on bills (STB-190): adds
bills.payment_method_id (FK -> payment_methods), backfills it by encrypting any
existing bills.payment_details into the owner's payment_methods (reusing a
matching method when one already exists), then drops the plaintext column.

Requires PAYMENT_ENC_KEY in the environment on prod (same key the app uses).

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-20

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Imported lazily so merely loading the migration graph never needs the app
    # package / crypto key — only the actual upgrade does.
    from app.utils import crypto

    conn = op.get_bind()

    # 1. New nullable FK column.
    with op.batch_alter_table('bills') as batch_op:
        batch_op.add_column(sa.Column('payment_method_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_bills_payment_method_id', 'payment_methods', ['payment_method_id'], ['id']
        )

    # 2. Backfill: each plaintext payment_details becomes an encrypted
    #    payment_methods row for the bill's owner (reusing a match if present).
    rows = conn.execute(
        sa.text(
            "SELECT id, owner_id, payment_details FROM bills "
            "WHERE payment_details IS NOT NULL AND payment_details <> ''"
        )
    ).fetchall()
    for bill_id, owner_id, value in rows:
        method_id = None
        existing = conn.execute(
            sa.text("SELECT id, enc_value FROM payment_methods WHERE user_id = :uid"),
            {"uid": owner_id},
        ).fetchall()
        for mid, enc in existing:
            try:
                if crypto.decrypt(enc) == value:
                    method_id = mid
                    break
            except Exception:
                pass
        if method_id is None:
            ts = datetime.utcnow()
            method_id = conn.execute(
                sa.text(
                    "INSERT INTO payment_methods (user_id, enc_value, created_at, updated_at) "
                    "VALUES (:uid, :enc, :ts, :ts) RETURNING id"
                ),
                {"uid": owner_id, "enc": crypto.encrypt(value), "ts": ts},
            ).scalar()
        conn.execute(
            sa.text("UPDATE bills SET payment_method_id = :mid WHERE id = :bid"),
            {"mid": method_id, "bid": bill_id},
        )

    # 3. Drop the plaintext column.
    with op.batch_alter_table('bills') as batch_op:
        batch_op.drop_column('payment_details')


def downgrade() -> None:
    from app.utils import crypto

    conn = op.get_bind()

    with op.batch_alter_table('bills') as batch_op:
        batch_op.add_column(sa.Column('payment_details', sa.String(), nullable=True))

    rows = conn.execute(
        sa.text(
            "SELECT b.id, p.enc_value FROM bills b "
            "JOIN payment_methods p ON p.id = b.payment_method_id "
            "WHERE b.payment_method_id IS NOT NULL"
        )
    ).fetchall()
    for bill_id, enc in rows:
        try:
            value = crypto.decrypt(enc)
        except Exception:
            value = None
        if value is not None:
            conn.execute(
                sa.text("UPDATE bills SET payment_details = :v WHERE id = :bid"),
                {"v": value, "bid": bill_id},
            )

    with op.batch_alter_table('bills') as batch_op:
        batch_op.drop_constraint('fk_bills_payment_method_id', type_='foreignkey')
        batch_op.drop_column('payment_method_id')
