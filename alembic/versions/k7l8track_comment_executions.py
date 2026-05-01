"""comment executions + limits config (PR-8g)

Revision ID: k7l8track
Revises: i5j6video
Create Date: 2026-05-01

PR-8g — 댓글 추적 + 영상당 한도.

⚠️ accounts 9 테이블 미변경 (절대 원칙).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'k7l8track'
down_revision: Union[str, Sequence[str], None] = 'i5j6video'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'comment_executions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('video_id', sa.String(),
                  sa.ForeignKey('videos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('slot_id', sa.Integer(),
                  sa.ForeignKey('comment_tree_slots.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('campaign_id', sa.Integer(),
                  sa.ForeignKey('campaigns.id', ondelete='SET NULL'), nullable=True),
        sa.Column('worker_id', sa.Integer(),
                  sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('posted_at', sa.DateTime(), nullable=False),
        sa.Column('youtube_comment_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='alive'),
        sa.Column('likes_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_checked_at', sa.DateTime(), nullable=True),
        sa.Column('next_check_at', sa.DateTime(), nullable=True),
        sa.Column('tracking_status', sa.String(20),
                  nullable=False, server_default='active'),
        sa.Column('tracking_phase', sa.String(20),
                  nullable=False, server_default='hour'),
        sa.Column('created_at', sa.DateTime(),
                  nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_executions_video', 'comment_executions', ['video_id'])
    op.create_index('ix_executions_worker', 'comment_executions', ['worker_id'])
    op.create_index('ix_executions_next_check', 'comment_executions', ['next_check_at'])
    op.create_index('ix_executions_status', 'comment_executions',
                    ['status', 'tracking_status'])

    # 한도 system_config seed
    op.execute("""
        INSERT INTO system_config (key, value)
        VALUES ('comment_limits',
          '{"large_max": 5, "medium_max": 3, "small_max": 1, "min_interval_minutes": 5, "channel_daily_max": 5, "video_pct_max": 0.05, "large_view_threshold": 1000000, "small_view_threshold": 10000, "viral_likes_threshold": 10}')
        ON CONFLICT (key) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DELETE FROM system_config WHERE key = 'comment_limits'")
    op.drop_index('ix_executions_status', table_name='comment_executions')
    op.drop_index('ix_executions_next_check', table_name='comment_executions')
    op.drop_index('ix_executions_worker', table_name='comment_executions')
    op.drop_index('ix_executions_video', table_name='comment_executions')
    op.drop_table('comment_executions')
