"""smart video collection — additive columns for pickup scoring + long-tail tracking + per-brand collection policy

Revision ID: a1b2c3d4e5f6
Revises: 6e20c5219262
Create Date: 2026-04-28

설계 원칙: 모두 additive. 기존 코드는 default 값으로 동작 유지.
- Video: 픽업 알고리즘용 메타 (last_worked_at, popularity_score, total_campaigns_count, discovered_via, discovery_keyword)
- Brand: 수집 정책 (collection_depth, longtail_count, scoring_weights JSON, preset_video_limit)
- Keyword: 변형 키워드 추적 (parent_keyword_id, is_variant)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '6e20c5219262'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Video — 픽업 메타 (last_worked_at 은 이미 존재) ──
    op.add_column('videos', sa.Column('total_campaigns_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('videos', sa.Column('popularity_score', sa.Float(), nullable=True))
    op.add_column('videos', sa.Column('discovered_via', sa.String(length=50), nullable=True))
    op.add_column('videos', sa.Column('discovery_keyword', sa.String(length=200), nullable=True))
    op.create_index('idx_videos_last_worked', 'videos', ['last_worked_at'])
    op.create_index('idx_videos_popularity', 'videos', ['popularity_score'])

    # ── Brand — 수집/픽업 정책 ──
    op.add_column('brands', sa.Column('collection_depth', sa.String(length=20), server_default='standard', nullable=False))
    op.add_column('brands', sa.Column('longtail_count', sa.Integer(), server_default='5', nullable=False))
    op.add_column('brands', sa.Column('scoring_weights', sa.Text(), nullable=True))  # JSON
    op.add_column('brands', sa.Column('preset_video_limit', sa.Integer(), server_default='1', nullable=False))

    # ── Keyword — 변형 추적 ──
    op.add_column('keywords', sa.Column('parent_keyword_id', sa.Integer(), nullable=True))
    op.add_column('keywords', sa.Column('is_variant', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.create_foreign_key(
        'fk_keywords_parent', 'keywords', 'keywords',
        ['parent_keyword_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('idx_keywords_parent', 'keywords', ['parent_keyword_id'])


def downgrade() -> None:
    op.drop_index('idx_keywords_parent', table_name='keywords')
    op.drop_constraint('fk_keywords_parent', 'keywords', type_='foreignkey')
    op.drop_column('keywords', 'is_variant')
    op.drop_column('keywords', 'parent_keyword_id')

    op.drop_column('brands', 'preset_video_limit')
    op.drop_column('brands', 'scoring_weights')
    op.drop_column('brands', 'longtail_count')
    op.drop_column('brands', 'collection_depth')

    op.drop_index('idx_videos_popularity', table_name='videos')
    op.drop_index('idx_videos_last_worked', table_name='videos')
    op.drop_column('videos', 'discovery_keyword')
    op.drop_column('videos', 'discovered_via')
    op.drop_column('videos', 'popularity_score')
    op.drop_column('videos', 'total_campaigns_count')
