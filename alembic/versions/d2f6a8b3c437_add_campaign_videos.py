"""add campaign_videos table for multi-video campaigns

Revision ID: d2f6a8b3c437
Revises: c9d3e5f7a224
Create Date: 2026-04-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd2f6a8b3c437'
down_revision: Union[str, Sequence[str], None] = 'c9d3e5f7a224'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'campaign_videos',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('campaign_id', sa.Integer(), sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('video_id', sa.String(), sa.ForeignKey('videos.id'), nullable=False),
        sa.Column('funnel_stage', sa.String(length=32), nullable=True),
        sa.Column('target_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('completed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('campaign_id', 'video_id', name='uq_campaign_video'),
    )
    op.create_index('idx_cvideo_campaign', 'campaign_videos', ['campaign_id'])
    op.create_index('idx_cvideo_video', 'campaign_videos', ['video_id'])


def downgrade() -> None:
    op.drop_index('idx_cvideo_video', table_name='campaign_videos')
    op.drop_index('idx_cvideo_campaign', table_name='campaign_videos')
    op.drop_table('campaign_videos')
