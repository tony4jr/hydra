"""niche messaging columns (PR-4d)

Revision ID: c1a4d2messaging
Revises: e6df17728bdc
Create Date: 2026-05-01

PR-4d — 메시지 탭. niches 테이블 7개 신규 컬럼 (Niche-scoped messaging + 페르소나).

선택 근거: 별도 persona/message 테이블 신설 대신 niches 컬럼 확장.
- 9 보호 테이블 (persona_slots 포함) 절대 미변경
- 단일 ALTER로 위험 최소화
- persona 슬롯 max 10 → JSON 배열로 충분 (관계형 분리 이득 미미)

⚠️ accounts 계열 9 테이블 (accounts, account_profile_history, profile_pools,
profile_locks, persona_slots, recovery_emails, ip_log, comment_snapshots,
action_log) — 본 마이그레이션에서 SELECT/UPDATE/INSERT/ALTER 0건.

백필: 기존 Niche row 의 brand 에서 core_message/tone_guide/target_audience/
mention_rules 복사 (default Niche 1:1 가정).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1a4d2messaging'
down_revision: Union[str, Sequence[str], None] = 'e6df17728bdc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 7 신규 컬럼 (모두 nullable, 기존 row 영향 0)
    op.add_column('niches', sa.Column('core_message', sa.Text(), nullable=True))
    op.add_column('niches', sa.Column('tone_guide', sa.Text(), nullable=True))
    op.add_column('niches', sa.Column('target_audience', sa.String(length=200), nullable=True))
    op.add_column('niches', sa.Column('mention_rules', sa.Text(), nullable=True))
    op.add_column('niches', sa.Column('personas_json', sa.Text(), nullable=True))
    op.add_column('niches', sa.Column('promotional_keywords', sa.Text(), nullable=True))
    op.add_column('niches', sa.Column('preset_selection', sa.Text(), nullable=True))

    # 2. Brand → Niche 백필 (default Niche 1:1)
    op.execute("""
        UPDATE niches SET
            core_message = b.core_message,
            tone_guide = b.tone_guide,
            target_audience = b.target_audience,
            mention_rules = b.mention_rules
        FROM brands b
        WHERE niches.brand_id = b.id
        AND niches.core_message IS NULL;
    """)


def downgrade() -> None:
    op.drop_column('niches', 'preset_selection')
    op.drop_column('niches', 'promotional_keywords')
    op.drop_column('niches', 'personas_json')
    op.drop_column('niches', 'mention_rules')
    op.drop_column('niches', 'target_audience')
    op.drop_column('niches', 'tone_guide')
    op.drop_column('niches', 'core_message')
