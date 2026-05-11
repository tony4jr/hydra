"""PR-C: worker_sessions + tasks.last_progress_at/last_phase + worker_progress.

Revision ID: x5y6workersess
Revises: w3x4likeminmax
Create Date: 2026-05-11 15:50:00.000000

Additive migration — nullable 컬럼 + 신규 테이블만. 다운그레이드 안전.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'x5y6workersess'
down_revision: Union[str, Sequence[str], None] = 'w3x4likeminmax'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. worker_sessions — 워커 측 세션 단위 heartbeat 추적.
    op.create_table(
        "worker_sessions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_uuid", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("worker_id", sa.Integer, sa.ForeignKey("workers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("last_heartbeat_at", sa.DateTime, nullable=True),
        sa.Column("ended_at", sa.DateTime, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("idx_wsess_worker_started", "worker_sessions", ["worker_id", "started_at"])
    op.create_index("idx_wsess_status_hb", "worker_sessions", ["status", "last_heartbeat_at"])

    # 2. tasks: last_progress_at, last_phase, session_uuid (workers 세션과 연결)
    op.add_column("tasks", sa.Column("last_progress_at", sa.DateTime, nullable=True))
    op.add_column("tasks", sa.Column("last_phase", sa.String(64), nullable=True))
    op.add_column("tasks", sa.Column("session_uuid", sa.String(64), nullable=True))
    op.create_index("idx_tasks_last_progress", "tasks", ["last_progress_at"])
    op.create_index("idx_tasks_session", "tasks", ["session_uuid"])
    # PR-C v2 — Codex 권장 복합 인덱스 (zombie cleanup 쿼리 효율)
    op.create_index("idx_tasks_status_lastprog", "tasks", ["status", "last_progress_at"])
    op.create_index("idx_tasks_status_startedat", "tasks", ["status", "started_at"])

    # 3. worker_progress — phase 변경 history (사고 후 시퀀스 reconstruction).
    op.create_table(
        "worker_progress",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_uuid", sa.String(64), nullable=False, index=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True),
        sa.Column("worker_id", sa.Integer, sa.ForeignKey("workers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("attempt_no", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sequence_no", sa.Integer, nullable=False, server_default="0"),
        sa.Column("phase", sa.String(64), nullable=False),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("occurred_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_wprog_session_seq", "worker_progress", ["session_uuid", "sequence_no"])
    op.create_index("idx_wprog_task_occ", "worker_progress", ["task_id", "occurred_at"])

    # 4. accounts.last_active_at index — suspend_guard 빠른 조회.
    op.create_index("idx_accounts_last_active", "accounts", ["status", "last_active_at"])


def downgrade() -> None:
    op.drop_index("idx_accounts_last_active", table_name="accounts")
    op.drop_index("idx_wprog_task_occ", table_name="worker_progress")
    op.drop_index("idx_wprog_session_seq", table_name="worker_progress")
    op.drop_table("worker_progress")
    op.drop_index("idx_tasks_status_startedat", table_name="tasks")
    op.drop_index("idx_tasks_status_lastprog", table_name="tasks")
    op.drop_index("idx_tasks_session", table_name="tasks")
    op.drop_index("idx_tasks_last_progress", table_name="tasks")
    op.drop_column("tasks", "session_uuid")
    op.drop_column("tasks", "last_phase")
    op.drop_column("tasks", "last_progress_at")
    op.drop_index("idx_wsess_status_hb", table_name="worker_sessions")
    op.drop_index("idx_wsess_worker_started", table_name="worker_sessions")
    op.drop_table("worker_sessions")
