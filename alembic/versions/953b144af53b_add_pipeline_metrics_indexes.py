"""add pipeline metrics indexes

Revision ID: 953b144af53b
Revises: b2c3d4e5f6a7
Create Date: 2026-04-29 23:41:19.841080

PR-2b-1 — pipeline_metrics service 의 윈도우 쿼리 성능용.
- videos.collected_at: discovered/market_fit stage 카운트
- tasks.created_at: task_created stage 카운트

둘 다 단일 컬럼 인덱스. composite 은 EXPLAIN 결과 보고 별도 PR.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '953b144af53b'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'idx_videos_collected_at',
        'videos',
        ['collected_at'],
    )
    op.create_index(
        'idx_tasks_created_at',
        'tasks',
        ['created_at'],
    )


def downgrade() -> None:
    op.drop_index('idx_tasks_created_at', table_name='tasks')
    op.drop_index('idx_videos_collected_at', table_name='videos')
