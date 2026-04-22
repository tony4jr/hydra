"""add_task_id_to_profile_locks

Revision ID: 11fae880a5dd
Revises: 442e3252987b
Create Date: 2026-04-22 22:17:31.543181

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '11fae880a5dd'
down_revision: Union[str, Sequence[str], None] = '442e3252987b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """profile_locks 에 task_id 추가 + 동시실행 방지 UNIQUE partial index.

    기존 profile_locks 테이블 재사용 (새 account_locks 안 만듦 — 꼬임 방지).
    변경:
    - task_id 컬럼 nullable 로 추가 (기존 row 는 NULL 유지)
    - UNIQUE (account_id) WHERE released_at IS NULL  — 동시 1개 active lock 보장
    """
    # 1. task_id 컬럼 추가 (SQLite + PG 호환 batch mode)
    with op.batch_alter_table("profile_locks") as batch:
        batch.add_column(sa.Column("task_id", sa.Integer, sa.ForeignKey("tasks.id"), nullable=True))

    # 2. UNIQUE partial index — 한 account 에 released_at IS NULL 인 lock 최대 1개
    # SQLite 3.8+ 및 PostgreSQL 모두 partial index 지원
    op.execute(
        "CREATE UNIQUE INDEX idx_profile_locks_active "
        "ON profile_locks (account_id) WHERE released_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_profile_locks_active")
    with op.batch_alter_table("profile_locks") as batch:
        batch.drop_column("task_id")
