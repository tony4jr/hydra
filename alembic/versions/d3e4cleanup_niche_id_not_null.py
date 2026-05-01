"""niche_id NOT NULL on keywords/campaigns (PR-3-cleanup)

Revision ID: d3e4cleanup
Revises: c1a4d2messaging
Create Date: 2026-05-01

PR-3-cleanup. Niche 모델 안정화 후 niche_id 강제.

⚠️ accounts 계열 9 테이블 (accounts, account_profile_history, profile_pools,
profile_locks, persona_slots, recovery_emails, ip_log, comment_snapshots,
action_log) — 본 마이그레이션에서 SELECT/UPDATE/INSERT/ALTER 0건.

범위 결정 (자율):
- keywords.niche_id, campaigns.niche_id: nullable → NOT NULL (백필 100% 검증됨)
- videos.niche_id: nullable 유지 (legacy row keyword_id NULL → niche_id NULL 1건 존재.
  manual 진입 영상도 가능성 있어 NOT NULL 제약 부적절)
- target_collection_config drop: 별도 PR (services TCC fallback 잔존, 8 컬럼 미흡수)
- brands deprecated columns drop: 별도 PR (admin_collection.py 의존)

사전 조건 검증 (prod):
- keywords NULL niche_id: 0
- campaigns NULL niche_id: 0
- videos NULL niche_id: 1 (keyword_id NULL legacy, NOT NULL 제외)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3e4cleanup'
down_revision: Union[str, Sequence[str], None] = 'c1a4d2messaging'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 사전 검증: NULL row 없어야 함 (PR-3a 백필 결과)
    op.execute("""
        DO $$
        DECLARE
            null_kw int;
            null_cp int;
        BEGIN
            SELECT count(*) INTO null_kw FROM keywords WHERE niche_id IS NULL;
            SELECT count(*) INTO null_cp FROM campaigns WHERE niche_id IS NULL;
            IF null_kw > 0 OR null_cp > 0 THEN
                RAISE EXCEPTION 'NOT NULL 변경 abort: keywords NULL=%, campaigns NULL=%',
                    null_kw, null_cp;
            END IF;
        END $$;
    """)

    op.alter_column('keywords', 'niche_id', nullable=False)
    op.alter_column('campaigns', 'niche_id', nullable=False)


def downgrade() -> None:
    op.alter_column('keywords', 'niche_id', nullable=True)
    op.alter_column('campaigns', 'niche_id', nullable=True)
