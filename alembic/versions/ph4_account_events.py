"""Phase 3.2 — account_events timeline

Revision ID: ph4acctevt
Revises: ph3sresol
Create Date: 2026-05-18

계정별 timeline. 매 task 결과/UNKNOWN/login 결과를 1줄씩 append.
운영자가 한 계정 클릭하면 최근 N건을 한눈에 볼 수 있어야 함.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "ph4acctevt"
down_revision: Union[str, Sequence[str], None] = "ph3sresol"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer,
                  sa.ForeignKey("accounts.id", name="fk_acctevt_account", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("worker_id", sa.Integer,
                  sa.ForeignKey("workers.id", name="fk_acctevt_worker", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("task_id", sa.Integer,
                  sa.ForeignKey("tasks.id", name="fk_acctevt_task", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        # task_start | task_complete | task_fail | login_success | login_fail
        # | unknown_screen | note | other
        sa.Column("screen_state", sa.String(64), nullable=True),
        sa.Column("failure_taxonomy", sa.String(32), nullable=True),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("context", sa.Text, nullable=True),  # JSON
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_acctevt_acct_time", "account_events", ["account_id", "created_at"])
    op.create_index("idx_acctevt_type_time", "account_events", ["event_type", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_acctevt_type_time", table_name="account_events")
    op.drop_index("idx_acctevt_acct_time", table_name="account_events")
    op.drop_table("account_events")
