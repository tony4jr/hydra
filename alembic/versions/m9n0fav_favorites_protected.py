"""favorites + protected videos (PR-8h)

Revision ID: m9n0fav
Revises: k7l8track
Create Date: 2026-05-01

PR-8h — 영상/채널 즐겨찾기 + 보호. PR-8 시리즈 마지막 sub-PR.

⚠️ accounts 9 테이블 미변경 (절대 원칙).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'm9n0fav'
down_revision: Union[str, Sequence[str], None] = 'k7l8track'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'favorite_channels',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('brand_id', sa.Integer(),
                  sa.ForeignKey('brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel_id', sa.String(), nullable=False),
        sa.Column('channel_title', sa.String(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(),
                  nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('brand_id', 'channel_id', name='uq_fav_channel'),
    )
    op.create_index('ix_fav_channel_brand', 'favorite_channels', ['brand_id'])

    op.create_table(
        'favorite_videos',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('brand_id', sa.Integer(),
                  sa.ForeignKey('brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('video_id', sa.String(),
                  sa.ForeignKey('videos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(),
                  nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('brand_id', 'video_id', name='uq_fav_video'),
    )
    op.create_index('ix_fav_video_brand', 'favorite_videos', ['brand_id'])

    op.create_table(
        'protected_videos',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('brand_id', sa.Integer(),
                  sa.ForeignKey('brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('video_id', sa.String(),
                  sa.ForeignKey('videos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(),
                  nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('brand_id', 'video_id', name='uq_protected_video'),
    )
    op.create_index('ix_protected_brand', 'protected_videos', ['brand_id'])


def downgrade() -> None:
    op.drop_index('ix_protected_brand', table_name='protected_videos')
    op.drop_table('protected_videos')
    op.drop_index('ix_fav_video_brand', table_name='favorite_videos')
    op.drop_table('favorite_videos')
    op.drop_index('ix_fav_channel_brand', table_name='favorite_channels')
    op.drop_table('favorite_channels')
