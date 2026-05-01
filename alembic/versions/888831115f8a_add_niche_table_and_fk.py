"""add niche table and fk

Revision ID: 888831115f8a
Revises: 953b144af53b
Create Date: 2026-05-01

PR-3a — Niche 모델 + FK 추가 (스키마만, 백필은 다음 마이그레이션).

⚠️ accounts 계열 9 테이블 미변경 (절대 원칙):
- accounts, account_profile_history, profile_pools, profile_locks,
  persona_slots, recovery_emails, ip_log, comment_snapshots, action_log
- 본 마이그레이션에서 SELECT/UPDATE/INSERT/ALTER 0건

PR-3a 변경 대상:
- niches 신규 테이블 (12 business 컬럼 + id/created_at/updated_at)
- keywords/campaigns/videos 의 niche_id FK (nullable, ondelete=SET NULL)
- ix_niches_brand_state (composite brand_id+state)
- idx_keywords/campaigns/videos_niche (단일 niche_id)

자율 결정 사항 (PR 본인 위임):
- ondelete: brand 측 RESTRICT (운영 안전), niche 측 SET NULL (데이터 보존)
- server_default 명시 (DB 일관성)
- DateTime timezone-naive (코드베이스 일관)
- collection_depth/state String(20) (PostgreSQL Enum 채택 X, 코드베이스 패턴)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '888831115f8a'
down_revision: Union[str, Sequence[str], None] = '953b144af53b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── niches 테이블 신설 ──────────────────────────────────────────
    op.create_table(
        'niches',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('brand_id', sa.Integer(),
                  sa.ForeignKey('brands.id', ondelete='RESTRICT'),
                  nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),

        # 시장 정의 (이전: TargetCollectionConfig)
        sa.Column('market_definition', sa.Text(), nullable=True),
        sa.Column('embedding_threshold', sa.Float(),
                  nullable=False, server_default='0.65'),

        # 우선순위 임계값
        sa.Column('trending_vph_threshold', sa.Integer(),
                  nullable=False, server_default='1000'),
        sa.Column('new_video_hours', sa.Integer(),
                  nullable=False, server_default='6'),
        sa.Column('long_term_score_threshold', sa.Integer(),
                  nullable=False, server_default='70'),

        # 수집 깊이 정책 (이전: Brand)
        sa.Column('collection_depth', sa.String(20),
                  nullable=False, server_default='standard'),
        sa.Column('keyword_variation_count', sa.Integer(),
                  nullable=False, server_default='5'),
        sa.Column('preset_per_video_limit', sa.Integer(),
                  nullable=False, server_default='1'),

        # 상태
        sa.Column('state', sa.String(20),
                  nullable=False, server_default='active'),

        sa.Column('created_at', sa.DateTime(),
                  nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(),
                  nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    op.create_index('ix_niches_brand_state', 'niches', ['brand_id', 'state'])

    # ─── 4 모델에 niche_id FK 추가 (nullable, ondelete=SET NULL) ──────
    op.add_column('keywords',
        sa.Column('niche_id', sa.Integer(),
                  sa.ForeignKey('niches.id', ondelete='SET NULL'),
                  nullable=True))
    op.create_index('idx_keywords_niche', 'keywords', ['niche_id'])

    op.add_column('campaigns',
        sa.Column('niche_id', sa.Integer(),
                  sa.ForeignKey('niches.id', ondelete='SET NULL'),
                  nullable=True))
    op.create_index('idx_campaigns_niche', 'campaigns', ['niche_id'])

    op.add_column('videos',
        sa.Column('niche_id', sa.Integer(),
                  sa.ForeignKey('niches.id', ondelete='SET NULL'),
                  nullable=True))
    op.create_index('idx_videos_niche', 'videos', ['niche_id'])


def downgrade() -> None:
    op.drop_index('idx_videos_niche', table_name='videos')
    op.drop_column('videos', 'niche_id')
    op.drop_index('idx_campaigns_niche', table_name='campaigns')
    op.drop_column('campaigns', 'niche_id')
    op.drop_index('idx_keywords_niche', table_name='keywords')
    op.drop_column('keywords', 'niche_id')
    op.drop_index('ix_niches_brand_state', table_name='niches')
    op.drop_table('niches')
