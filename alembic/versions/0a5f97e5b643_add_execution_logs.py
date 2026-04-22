"""add_execution_logs

Revision ID: 0a5f97e5b643
Revises: e71d571721f1
Create Date: 2026-04-22 22:06:30.755203

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a5f97e5b643'
down_revision: Union[str, Sequence[str], None] = 'e71d571721f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """워커가 태스크 실행 중 쏘는 로그 중앙 수집소.

    Phase 3 (관측성) 의 핵심 테이블. 어드민 UI 에서 태스크/워커/계정별
    타임라인 조회 + 필터링용.

    30일 이상 된 row 는 주기 크론으로 삭제 예정 (Phase 4).
    task_id 에 ON DELETE CASCADE — task 삭제 시 관련 로그도 자동 삭제.
    """
    op.create_table(
        "execution_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True),
        sa.Column("worker_id", sa.Integer, sa.ForeignKey("workers.id"), nullable=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("timestamp", sa.DateTime, nullable=False),
        sa.Column("level", sa.String(16), nullable=False),  # DEBUG / INFO / WARN / ERROR
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("context", sa.Text, nullable=True),       # JSON: {url, step, selector, ...}
        sa.Column("screenshot_url", sa.String(512), nullable=True),
    )
    op.create_index("idx_exec_task", "execution_logs", ["task_id"])
    op.create_index("idx_exec_worker_time", "execution_logs", ["worker_id", "timestamp"])
    op.create_index("idx_exec_account_time", "execution_logs", ["account_id", "timestamp"])


def downgrade() -> None:
    op.drop_index("idx_exec_account_time", "execution_logs")
    op.drop_index("idx_exec_worker_time", "execution_logs")
    op.drop_index("idx_exec_task", "execution_logs")
    op.drop_table("execution_logs")
