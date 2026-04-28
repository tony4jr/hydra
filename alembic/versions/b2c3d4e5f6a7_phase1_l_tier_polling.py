"""phase1: L tier + lifecycle phase + polling tiers + global state + collection config

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-28

Phase 1 명세 채택 (사용자 보강 반영):
- videos: L tier, lifecycle phase, embedding score, state, top_comment_likes 등
- keywords: tier (core/expansion/long_tail), is_negative, poll_5min/30min/daily
- 신규 테이블: target_collection_config, youtube_video_global_state,
              video_keyword_matches, channel_blacklist,
              target_category_fitness, video_collection_log

설계 원칙: additive only. Brand=Target 동일시 (target_id := brands.id).
기존 코드는 default 값으로 동작 유지.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Videos — L tier, Phase, embedding, state, 추가 메타 ──
    op.add_column('videos', sa.Column('l_tier', sa.String(2), nullable=True))
    op.add_column('videos', sa.Column('lifecycle_phase', sa.SmallInteger(), nullable=True))
    op.add_column('videos', sa.Column('category_subtype', sa.String(50), nullable=True))
    op.add_column('videos', sa.Column('embedding_score', sa.Float(), nullable=True))
    op.add_column('videos', sa.Column('our_presence_score', sa.Float(), server_default='0', nullable=False))
    op.add_column('videos', sa.Column('total_scenarios_run', sa.Integer(), server_default='0', nullable=False))
    op.add_column('videos', sa.Column('last_action_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('videos', sa.Column('next_revisit_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('videos', sa.Column('state', sa.String(20), server_default='pending', nullable=False))
    op.add_column('videos', sa.Column('blacklist_reason', sa.String(100), nullable=True))
    op.add_column('videos', sa.Column('top_comment_likes', sa.Integer(), server_default='0', nullable=False))
    op.add_column('videos', sa.Column('view_count_prev_day', sa.Integer(), server_default='0', nullable=False))
    op.add_column('videos', sa.Column('views_per_hour_recent', sa.Float(), server_default='0', nullable=False))
    op.add_column('videos', sa.Column('relevance_score_v2', sa.Float(), nullable=True))  # Phase 2 5점수 합산용 (기존 popularity_score 와 별개)

    op.create_index('idx_videos_l_tier', 'videos', ['l_tier'])
    op.create_index('idx_videos_state', 'videos', ['state'])
    op.create_index('idx_videos_next_revisit', 'videos', ['next_revisit_at'])
    op.create_index('idx_videos_lifecycle', 'videos', ['lifecycle_phase'])

    # ── Keywords — tier + 폴링 빈도 ──
    op.add_column('keywords', sa.Column('keyword_tier', sa.String(20), server_default='core', nullable=False))
    op.add_column('keywords', sa.Column('is_negative', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('keywords', sa.Column('poll_5min', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('keywords', sa.Column('poll_30min', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('keywords', sa.Column('poll_daily', sa.Boolean(), server_default=sa.text('true'), nullable=False))

    op.create_index('idx_keywords_poll_5min', 'keywords', ['poll_5min'])
    op.create_index('idx_keywords_poll_30min', 'keywords', ['poll_30min'])
    op.create_index('idx_keywords_negative', 'keywords', ['is_negative'])

    # ── Target Collection Config (target_id := brands.id) ──
    op.create_table(
        'target_collection_config',
        sa.Column('target_id', sa.Integer(), sa.ForeignKey('brands.id', ondelete='CASCADE'), primary_key=True),
        # L1 풀
        sa.Column('l1_threshold_score', sa.Float(), server_default='70.0', nullable=False),
        sa.Column('l1_max_pool_size', sa.Integer(), server_default='1000', nullable=False),
        # L2
        sa.Column('l2_max_age_hours', sa.Integer(), server_default='24', nullable=False),
        sa.Column('l2_min_channel_subscribers', sa.Integer(), server_default='10000', nullable=False),
        # L3
        sa.Column('l3_views_per_hour_threshold', sa.Integer(), server_default='1000', nullable=False),
        sa.Column('l3_views_24h_threshold', sa.Integer(), server_default='10000', nullable=False),
        # 임베딩
        sa.Column('embedding_reference_text', sa.Text(), nullable=True),
        sa.Column('embedding_threshold', sa.Float(), server_default='0.65', nullable=False),
        # 룰 필터
        sa.Column('hard_block_min_video_seconds', sa.Integer(), server_default='30', nullable=False),
        sa.Column('exclude_kids_category', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('exclude_live_streaming', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        # 점수 가중치 (JSON 텍스트)
        sa.Column('score_weights', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    )

    # ── 글로벌 상태 추적 (같은 영상 다중 타겟 작전 충돌 방지) ──
    op.create_table(
        'youtube_video_global_state',
        sa.Column('youtube_video_id', sa.String(20), primary_key=True),
        sa.Column('total_actions_24h', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_actions_7d', sa.Integer(), server_default='0', nullable=False),
        sa.Column('active_target_count', sa.SmallInteger(), server_default='0', nullable=False),
        sa.Column('active_scenario_count', sa.SmallInteger(), server_default='0', nullable=False),
        sa.Column('last_action_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_main_comment_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('recent_action_log', sa.Text(), nullable=True),  # JSON array
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    )
    op.create_index('idx_global_state_actions_24h', 'youtube_video_global_state', ['total_actions_24h'])

    # ── 키워드 매칭 (검색 노출도 점수용) ──
    op.create_table(
        'video_keyword_matches',
        sa.Column('match_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('video_id', sa.String(), sa.ForeignKey('videos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('keyword_id', sa.Integer(), sa.ForeignKey('keywords.id'), nullable=False),
        sa.Column('search_rank', sa.SmallInteger(), nullable=True),
        sa.Column('matched_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.UniqueConstraint('video_id', 'keyword_id', name='uq_video_keyword'),
    )
    op.create_index('idx_match_video', 'video_keyword_matches', ['video_id'])

    # ── 채널 블랙리스트 ──
    op.create_table(
        'channel_blacklist',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('channel_id', sa.String(50), nullable=False),
        sa.Column('target_id', sa.Integer(), sa.ForeignKey('brands.id', ondelete='CASCADE'), nullable=True),  # NULL = global
        sa.Column('reason', sa.String(100), nullable=True),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.UniqueConstraint('channel_id', 'target_id', name='uq_channel_target'),
    )
    op.create_index('idx_channel_blacklist_global', 'channel_blacklist', ['channel_id'])

    # ── 카테고리 적합도 (Phase 2에서 본격 사용, 모델만 미리) ──
    op.create_table(
        'target_category_fitness',
        sa.Column('target_id', sa.Integer(), sa.ForeignKey('brands.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('category', sa.String(50), primary_key=True),
        sa.Column('fitness', sa.Float(), server_default='0.5', nullable=False),
    )

    # ── 수집 로그 (운영 디버그용) ──
    op.create_table(
        'video_collection_log',
        sa.Column('log_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('poll_type', sa.String(20), nullable=True),  # 5min|30min|daily|manual
        sa.Column('keywords_processed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('api_calls_made', sa.Integer(), server_default='0', nullable=False),
        sa.Column('videos_found', sa.Integer(), server_default='0', nullable=False),
        sa.Column('videos_new', sa.Integer(), server_default='0', nullable=False),
        sa.Column('videos_updated', sa.Integer(), server_default='0', nullable=False),
        sa.Column('videos_blocked', sa.Integer(), server_default='0', nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),  # running|done|error
        sa.Column('error_message', sa.Text(), nullable=True),
    )
    op.create_index('idx_collection_log_target_started', 'video_collection_log', ['target_id', 'started_at'])

    # ── YouTube API quota 모니터링 ──
    op.create_table(
        'youtube_quota_log',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('api_key_index', sa.Integer(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('quota_used', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_request_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('api_key_index', 'day', name='uq_quota_per_day'),
    )
    op.create_index('idx_quota_day', 'youtube_quota_log', ['day'])


def downgrade() -> None:
    op.drop_index('idx_quota_day', table_name='youtube_quota_log')
    op.drop_table('youtube_quota_log')

    op.drop_index('idx_collection_log_target_started', table_name='video_collection_log')
    op.drop_table('video_collection_log')

    op.drop_table('target_category_fitness')

    op.drop_index('idx_channel_blacklist_global', table_name='channel_blacklist')
    op.drop_table('channel_blacklist')

    op.drop_index('idx_match_video', table_name='video_keyword_matches')
    op.drop_table('video_keyword_matches')

    op.drop_index('idx_global_state_actions_24h', table_name='youtube_video_global_state')
    op.drop_table('youtube_video_global_state')

    op.drop_table('target_collection_config')

    op.drop_index('idx_keywords_negative', table_name='keywords')
    op.drop_index('idx_keywords_poll_30min', table_name='keywords')
    op.drop_index('idx_keywords_poll_5min', table_name='keywords')
    op.drop_column('keywords', 'poll_daily')
    op.drop_column('keywords', 'poll_30min')
    op.drop_column('keywords', 'poll_5min')
    op.drop_column('keywords', 'is_negative')
    op.drop_column('keywords', 'keyword_tier')

    op.drop_index('idx_videos_lifecycle', table_name='videos')
    op.drop_index('idx_videos_next_revisit', table_name='videos')
    op.drop_index('idx_videos_state', table_name='videos')
    op.drop_index('idx_videos_l_tier', table_name='videos')
    op.drop_column('videos', 'relevance_score_v2')
    op.drop_column('videos', 'views_per_hour_recent')
    op.drop_column('videos', 'view_count_prev_day')
    op.drop_column('videos', 'top_comment_likes')
    op.drop_column('videos', 'blacklist_reason')
    op.drop_column('videos', 'state')
    op.drop_column('videos', 'next_revisit_at')
    op.drop_column('videos', 'last_action_at')
    op.drop_column('videos', 'total_scenarios_run')
    op.drop_column('videos', 'our_presence_score')
    op.drop_column('videos', 'embedding_score')
    op.drop_column('videos', 'category_subtype')
    op.drop_column('videos', 'lifecycle_phase')
    op.drop_column('videos', 'l_tier')
