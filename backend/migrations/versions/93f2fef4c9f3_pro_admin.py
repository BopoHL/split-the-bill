"""Pro as the admin manages it: Telegram's subscriptions known by their first
payment, and grants taken back or refunded.

Revision ID: 93f2fef4c9f3
Revises: e5bd630db327
Create Date: 2026-10-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "93f2fef4c9f3"
down_revision: Union[str, Sequence[str], None] = "e5bd630db327"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pro_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("charge_id", sa.String(length=255), nullable=False),
        sa.Column("renewal_canceled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("charge_id"),
    )
    op.create_index("ix_pro_subscriptions_user_id", "pro_subscriptions", ["user_id"])
    op.add_column("pro_grants", sa.Column("subscription_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_pro_grants_subscription", "pro_grants", "pro_subscriptions", ["subscription_id"], ["id"])
    op.create_index("ix_pro_grants_subscription_id", "pro_grants", ["subscription_id"])
    op.add_column("pro_grants", sa.Column("revoked_at", sa.DateTime(), nullable=True))
    op.add_column("pro_grants", sa.Column("refunded_at", sa.DateTime(), nullable=True))

    # Subscriptions are younger than a month, so every month paid so far is the
    # first payment of its own subscription.
    op.execute(
        "INSERT INTO pro_subscriptions (user_id, charge_id, created_at, updated_at) "
        "SELECT user_id, charge_id, created_at, created_at FROM pro_grants "
        "WHERE source = 'subscription' AND charge_id IS NOT NULL"
    )
    op.execute(
        "UPDATE pro_grants SET subscription_id = pro_subscriptions.id FROM pro_subscriptions "
        "WHERE pro_subscriptions.charge_id = pro_grants.charge_id"
    )


def downgrade() -> None:
    op.drop_column("pro_grants", "refunded_at")
    op.drop_column("pro_grants", "revoked_at")
    op.drop_index("ix_pro_grants_subscription_id", table_name="pro_grants")
    op.drop_constraint("fk_pro_grants_subscription", "pro_grants", type_="foreignkey")
    op.drop_column("pro_grants", "subscription_id")
    op.drop_index("ix_pro_subscriptions_user_id", table_name="pro_subscriptions")
    op.drop_table("pro_subscriptions")
