"""Phase 4 Slice 4.1a — terminal_sessions table + lifecycle + partial unique

Revision ID: e3f4g5termses
Revises: d2e3f4adunq
Create Date: 2026-05-13

웹 터미널 세션 schema. admin_agent 워커에 persistent shell process 띄워
인터랙티브 흐름. partial unique index 로 같은 worker 에 active session
1개만 강제.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e3f4g5termses"
down_revision: Union[str, Sequence[str], None] = "d2e3f4adunq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_UNIQ_WHERE = "status IN ('pending', 'active', 'closing')"


def upgrade() -> None:
    op.create_table(
        "terminal_sessions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "worker_id", sa.Integer,
            sa.ForeignKey("workers.id", name="fk_terminal_worker", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "opened_by", sa.Integer,
            sa.ForeignKey("users.id", name="fk_terminal_user"),
            nullable=True,
        ),
        sa.Column("opened_at", sa.DateTime, nullable=False),
        sa.Column("last_activity_at", sa.DateTime, nullable=False),
        sa.Column("closing_at", sa.DateTime, nullable=True),
        sa.Column("closed_at", sa.DateTime, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("shell", sa.String(16), nullable=False, server_default="powershell"),
        sa.Column("session_token", sa.String(64), nullable=False, unique=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index(
        "idx_terminal_worker_status", "terminal_sessions",
        ["worker_id", "status"],
    )
    op.create_index(
        "idx_terminal_last_activity", "terminal_sessions",
        ["last_activity_at"],
    )
    op.create_index(
        "uq_terminal_active_session_per_worker", "terminal_sessions",
        ["worker_id"], unique=True,
        postgresql_where=sa.text(_UNIQ_WHERE),
        sqlite_where=sa.text(_UNIQ_WHERE),
    )


def downgrade() -> None:
    op.drop_index("uq_terminal_active_session_per_worker", table_name="terminal_sessions")
    op.drop_index("idx_terminal_last_activity", table_name="terminal_sessions")
    op.drop_index("idx_terminal_worker_status", table_name="terminal_sessions")
    op.drop_table("terminal_sessions")
