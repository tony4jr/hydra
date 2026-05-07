"""multi-brand: Product, NichePresetSelection, Slot intent/tone/mention, GlobalAdPhraseBlocklist

Revision ID: u9v0multibrand
Revises: s7t8slotengine
Create Date: 2026-05-07

PR-A — Brand → Product → Niche 3-tier + 의도 설명형 슬롯 + 광고 어휘 blocklist.
Additive only — 기존 text_template / Niche.comment_preset_id 보존.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'u9v0multibrand'
down_revision: Union[str, Sequence[str], None] = 's7t8slotengine'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) products 테이블
    op.create_table(
        'products',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('brand_id', sa.Integer, sa.ForeignKey('brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_name', sa.String(120), nullable=False),
        sa.Column('protected_terms', sa.Text),
        sa.Column('core_keywords', sa.Text),
        sa.Column('description', sa.Text),
        sa.Column('core_message', sa.Text),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index('ix_products_brand', 'products', ['brand_id'])

    # 2) Niche.product_id
    op.add_column(
        'niches',
        sa.Column('product_id', sa.Integer, sa.ForeignKey('products.id', ondelete='SET NULL'), nullable=True),
    )

    # 3) Slot 컬럼 추가
    op.add_column('comment_tree_slots',
                  sa.Column('intent', sa.Text, nullable=True))
    op.add_column('comment_tree_slots',
                  sa.Column('tone_anchor', sa.Text, nullable=True))
    op.add_column('comment_tree_slots',
                  sa.Column('mention_brand', sa.Boolean, nullable=False, server_default=sa.text('0')))
    op.add_column('comment_tree_slots',
                  sa.Column('mention_solution', sa.Boolean, nullable=False, server_default=sa.text('0')))

    # 4) niche_preset_selections 테이블
    op.create_table(
        'niche_preset_selections',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('niche_id', sa.Integer, sa.ForeignKey('niches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('preset_id', sa.Integer, sa.ForeignKey('comment_presets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('weight', sa.Integer, nullable=False, server_default='10'),
        sa.Column('enabled', sa.Boolean, nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint('niche_id', 'preset_id', name='uq_niche_preset'),
    )
    op.create_index('ix_nps_niche', 'niche_preset_selections', ['niche_id'])

    # 5) global_ad_phrase_blocklist
    op.create_table(
        'global_ad_phrase_blocklist',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('phrase', sa.String(120), nullable=False, unique=True),
        sa.Column('added_by_user_id', sa.Integer, nullable=True),
        sa.Column('added_at', sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index('ix_global_blocklist_phrase', 'global_ad_phrase_blocklist', ['phrase'])

    # 6) 데이터 백필 — 기존 Brand 마다 Product 1개 자동 생성
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO products (brand_id, product_name, core_keywords, description, core_message,
                              created_at, updated_at)
        SELECT id,
               COALESCE(product_name, name),
               COALESCE(allowed_keywords, '[]'),
               '', COALESCE(core_message, ''),
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM brands
        WHERE NOT EXISTS (SELECT 1 FROM products p WHERE p.brand_id = brands.id)
    """))

    # 7) Niche.product_id 백필 — 같은 brand_id 의 첫 product 로 매핑
    conn.execute(sa.text("""
        UPDATE niches
        SET product_id = (
            SELECT MIN(p.id) FROM products p WHERE p.brand_id = niches.brand_id
        )
        WHERE product_id IS NULL AND brand_id IS NOT NULL
    """))

    # 8) Niche.comment_preset_id 가 있던 행 → NichePresetSelection 으로 이전
    conn.execute(sa.text("""
        INSERT INTO niche_preset_selections (niche_id, preset_id, weight, enabled, created_at)
        SELECT id, comment_preset_id, 100, 1, CURRENT_TIMESTAMP
        FROM niches
        WHERE comment_preset_id IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM niche_preset_selections nps
            WHERE nps.niche_id = niches.id AND nps.preset_id = niches.comment_preset_id
        )
    """))


def downgrade() -> None:
    op.drop_index('ix_global_blocklist_phrase', table_name='global_ad_phrase_blocklist')
    op.drop_table('global_ad_phrase_blocklist')

    op.drop_index('ix_nps_niche', table_name='niche_preset_selections')
    op.drop_table('niche_preset_selections')

    op.drop_column('comment_tree_slots', 'mention_solution')
    op.drop_column('comment_tree_slots', 'mention_brand')
    op.drop_column('comment_tree_slots', 'tone_anchor')
    op.drop_column('comment_tree_slots', 'intent')

    op.drop_column('niches', 'product_id')

    op.drop_index('ix_products_brand', table_name='products')
    op.drop_table('products')
