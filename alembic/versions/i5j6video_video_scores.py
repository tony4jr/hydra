"""video scores + is_longrun (PR-8f)

Revision ID: i5j6video
Revises: h3i4preset
Create Date: 2026-05-01

PR-8f — 영상 점수 (100점) + 부스트 + 안전필터 + 롱런 분류.

⚠️ accounts 9 테이블 미변경 (절대 원칙).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'i5j6video'
down_revision: Union[str, Sequence[str], None] = 'h3i4preset'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'video_scores',
        sa.Column('video_id', sa.String(),
                  sa.ForeignKey('videos.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('recency_score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('view_score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('keyword_score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('boost_favorite_channel', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('boost_favorite_video', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('safety_filter_reason', sa.String(60), nullable=True),
        sa.Column('calculated_at', sa.DateTime(),
                  nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_video_scores_total', 'video_scores', ['total_score'])

    # Video.is_longrun 컬럼
    op.add_column('videos',
        sa.Column('is_longrun', sa.Boolean(), nullable=False, server_default='false'))

    # 가중치 system_config seed
    op.execute("""
        INSERT INTO system_config (key, value)
        VALUES ('video_score_weights',
          '{"recency": 40, "view": 30, "keyword": 30, "boost_channel": 20, "boost_video": 50, "longrun_threshold": 10000}')
        ON CONFLICT (key) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DELETE FROM system_config WHERE key = 'video_score_weights'")
    op.drop_column('videos', 'is_longrun')
    op.drop_index('ix_video_scores_total', table_name='video_scores')
    op.drop_table('video_scores')
