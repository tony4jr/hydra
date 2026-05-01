"""backfill niche from brand and target_collection_config

Revision ID: e6df17728bdc
Revises: 888831115f8a
Create Date: 2026-05-01

PR-3a — Niche 백필. Brand + TargetCollectionConfig → default Niche 생성.

⚠️ accounts 계열 9 테이블 미변경 (절대 원칙):
- accounts, account_profile_history, profile_pools, profile_locks,
  persona_slots, recovery_emails, ip_log, comment_snapshots, action_log
- 본 마이그레이션에서 SELECT/UPDATE/INSERT 0건

백필 흐름:
1. 각 Brand 마다 default Niche INSERT
   - Brand 컬럼: collection_depth, longtail_count, preset_video_limit
   - TargetCollectionConfig 컬럼: embedding_reference_text, embedding_threshold,
     l1_threshold_score, l3_views_per_hour_threshold (LEFT JOIN, FK target_id)
   - 신규: new_video_hours (default 6)
   - target_collection_config 가 비어있으면 LEFT JOIN + COALESCE 로 default 적용
2. Keyword 의 niche_id 채움 (brand_id 경유)
3. Campaign 의 niche_id 채움 (brand_id 경유)
4. Video 의 niche_id 채움 (keyword 경유, videos 에 brand_id 없음)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e6df17728bdc'
down_revision: Union[str, Sequence[str], None] = '888831115f8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 각 Brand 마다 default Niche INSERT (1:1).
    #    TargetCollectionConfig 가 있으면 그 값 사용, 없으면 default.
    #    target_collection_config.target_id = brands.id 로 매칭.
    op.execute("""
        INSERT INTO niches (
            brand_id, name, description,
            market_definition, embedding_threshold,
            trending_vph_threshold, new_video_hours, long_term_score_threshold,
            collection_depth, keyword_variation_count, preset_per_video_limit,
            state, created_at, updated_at
        )
        SELECT
            b.id                                                 AS brand_id,
            COALESCE(b.name, '기본 시장')                          AS name,
            '자동 마이그레이션됨 (PR-3a)'                            AS description,
            tcc.embedding_reference_text                         AS market_definition,
            COALESCE(tcc.embedding_threshold, 0.65)              AS embedding_threshold,
            COALESCE(tcc.l3_views_per_hour_threshold, 1000)      AS trending_vph_threshold,
            6                                                     AS new_video_hours,
            COALESCE(CAST(tcc.l1_threshold_score AS INTEGER), 70) AS long_term_score_threshold,
            COALESCE(b.collection_depth, 'standard')             AS collection_depth,
            COALESCE(b.longtail_count, 5)                        AS keyword_variation_count,
            COALESCE(b.preset_video_limit, 1)                    AS preset_per_video_limit,
            'active'                                              AS state,
            CURRENT_TIMESTAMP                                     AS created_at,
            CURRENT_TIMESTAMP                                     AS updated_at
        FROM brands b
        LEFT JOIN target_collection_config tcc ON tcc.target_id = b.id
        WHERE NOT EXISTS (
            SELECT 1 FROM niches n WHERE n.brand_id = b.id
        );
    """)

    # 2. Keyword 의 niche_id (brand_id 경유)
    op.execute("""
        UPDATE keywords
        SET niche_id = (
            SELECT n.id FROM niches n
            WHERE n.brand_id = keywords.brand_id
            ORDER BY n.id ASC LIMIT 1
        )
        WHERE keywords.niche_id IS NULL AND keywords.brand_id IS NOT NULL;
    """)

    # 3. Campaign 의 niche_id (brand_id 경유)
    op.execute("""
        UPDATE campaigns
        SET niche_id = (
            SELECT n.id FROM niches n
            WHERE n.brand_id = campaigns.brand_id
            ORDER BY n.id ASC LIMIT 1
        )
        WHERE campaigns.niche_id IS NULL AND campaigns.brand_id IS NOT NULL;
    """)

    # 4. Video 의 niche_id (keyword 경유, videos 에 brand_id 없음)
    op.execute("""
        UPDATE videos
        SET niche_id = (
            SELECT k.niche_id FROM keywords k
            WHERE k.id = videos.keyword_id AND k.niche_id IS NOT NULL
            LIMIT 1
        )
        WHERE videos.niche_id IS NULL AND videos.keyword_id IS NOT NULL;
    """)


def downgrade() -> None:
    # 데이터 NULL 처리 (테이블/컬럼은 유지, 다음 downgrade 에서 drop)
    op.execute("UPDATE videos SET niche_id = NULL")
    op.execute("UPDATE campaigns SET niche_id = NULL")
    op.execute("UPDATE keywords SET niche_id = NULL")
    op.execute("DELETE FROM niches")
