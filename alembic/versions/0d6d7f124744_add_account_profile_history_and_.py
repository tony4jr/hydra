"""add account_profile_history and adspower uq

Revision ID: 0d6d7f124744
Revises: 5ae7d3c20819
Create Date: 2026-04-18 12:02:40.811509

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0d6d7f124744'
down_revision: Union[str, Sequence[str], None] = '5ae7d3c20819'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "account_profile_history",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("worker_id", sa.Integer(), sa.ForeignKey("workers.id"), nullable=True),
        sa.Column("adspower_profile_id", sa.String(), nullable=False),
        sa.Column("fingerprint_snapshot", sa.Text(), nullable=True),
        sa.Column("created_source", sa.String(), nullable=False, server_default="auto"),
        sa.Column("device_hint", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("retired_at", sa.DateTime(), nullable=True),
        sa.Column("retire_reason", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_profhist_account", "account_profile_history", ["account_id"])
    op.create_index("idx_profhist_active", "account_profile_history",
                    ["account_id", "retired_at"])

    # Backfill: any account with adspower_profile_id → history row (manual_mapped)
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, adspower_profile_id FROM accounts "
        "WHERE adspower_profile_id IS NOT NULL AND adspower_profile_id != ''"
    )).fetchall()
    for acc_id, pid in rows:
        conn.execute(sa.text(
            "INSERT INTO account_profile_history "
            "(account_id, adspower_profile_id, created_source, created_at) "
            "VALUES (:a, :p, 'manual_mapped', CURRENT_TIMESTAMP)"
        ), {"a": acc_id, "p": pid})

    # Add UNIQUE on accounts.adspower_profile_id. SQLite + Postgres both treat
    # NULL as distinct for UNIQUE, so partial index not strictly needed.
    with op.batch_alter_table("accounts") as batch:
        batch.create_unique_constraint(
            "uq_accounts_adspower_profile_id", ["adspower_profile_id"]
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("accounts") as batch:
        batch.drop_constraint("uq_accounts_adspower_profile_id", type_="unique")
    op.drop_index("idx_profhist_active", table_name="account_profile_history")
    op.drop_index("idx_profhist_account", table_name="account_profile_history")
    op.drop_table("account_profile_history")
