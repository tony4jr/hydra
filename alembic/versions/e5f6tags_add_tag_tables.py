"""add tag tables (PR-6)

Revision ID: e5f6tags
Revises: d3e4cleanup
Create Date: 2026-05-01

PR-6 — 자유 태그. tags 테이블 + niche_tags / campaign_tags N:M.

⚠️ accounts 계열 9 테이블 (accounts, account_profile_history, profile_pools,
profile_locks, persona_slots, recovery_emails, ip_log, comment_snapshots,
action_log) — 본 마이그레이션에서 SELECT/UPDATE/INSERT/ALTER 0건.

테이블명 정정 (spec 의 tag/niche_tag/campaign_tag → 코드베이스 plural 일치):
- tags / niche_tags / campaign_tags
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6tags'
down_revision: Union[str, Sequence[str], None] = 'd3e4cleanup'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tags',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('namespace', sa.String(60), nullable=False),
        sa.Column('value', sa.String(120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(),
                  nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('namespace', 'value', name='uq_tags_ns_value'),
    )
    op.create_index('ix_tags_namespace', 'tags', ['namespace'])

    op.create_table(
        'niche_tags',
        sa.Column('niche_id', sa.Integer(),
                  sa.ForeignKey('niches.id', ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('tag_id', sa.Integer(),
                  sa.ForeignKey('tags.id', ondelete='CASCADE'),
                  primary_key=True),
    )
    op.create_index('ix_niche_tags_tag', 'niche_tags', ['tag_id'])

    op.create_table(
        'campaign_tags',
        sa.Column('campaign_id', sa.Integer(),
                  sa.ForeignKey('campaigns.id', ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('tag_id', sa.Integer(),
                  sa.ForeignKey('tags.id', ondelete='CASCADE'),
                  primary_key=True),
    )
    op.create_index('ix_campaign_tags_tag', 'campaign_tags', ['tag_id'])


def downgrade() -> None:
    op.drop_index('ix_campaign_tags_tag', table_name='campaign_tags')
    op.drop_table('campaign_tags')
    op.drop_index('ix_niche_tags_tag', table_name='niche_tags')
    op.drop_table('niche_tags')
    op.drop_index('ix_tags_namespace', table_name='tags')
    op.drop_table('tags')
