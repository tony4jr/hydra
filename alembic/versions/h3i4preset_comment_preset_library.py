"""comment preset library (PR-8d)

Revision ID: h3i4preset
Revises: f1g2brand
Create Date: 2026-05-01

PR-8d — 댓글 트리 프리셋 라이브러리.

⚠️ 자율 spec 정정: 기존 'presets' 테이블 (campaign step 시퀀스, code/steps JSON 사용 중) 과
   충돌 회피 — 신규 테이블명 'comment_presets', 'comment_tree_slots' 사용.
   Niche FK 도 'comment_preset_id' (spec 의 'preset_id' 가 아님).

⚠️ accounts 계열 9 테이블 미변경 (절대 원칙).

5 기본 시드: 후기형 / 공감형 / 비교형 / 정보형 / 질문형.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'h3i4preset'
down_revision: Union[str, Sequence[str], None] = 'f1g2brand'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # comment_presets 테이블
    op.create_table(
        'comment_presets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_global', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(),
                  nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(),
                  nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # comment_tree_slots 테이블
    op.create_table(
        'comment_tree_slots',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('comment_preset_id', sa.Integer(),
                  sa.ForeignKey('comment_presets.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('slot_label', sa.String(4), nullable=False),
        sa.Column('reply_to_slot_label', sa.String(4), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('text_template', sa.Text(), nullable=True),
        sa.Column('length', sa.String(10), nullable=False, server_default='medium'),
        sa.Column('emoji', sa.String(10), nullable=False, server_default='sometimes'),
        sa.Column('ai_variation', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('like_min', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('like_max', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('like_distribution', sa.String(10),
                  nullable=False, server_default='adaptive'),
        sa.UniqueConstraint('comment_preset_id', 'slot_label',
                            name='uq_slots_preset_label'),
    )
    op.create_index('ix_slots_preset', 'comment_tree_slots', ['comment_preset_id'])

    # Niche.comment_preset_id FK
    op.add_column('niches', sa.Column(
        'comment_preset_id', sa.Integer(),
        sa.ForeignKey('comment_presets.id', ondelete='SET NULL'), nullable=True
    ))
    op.create_index('idx_niches_comment_preset', 'niches', ['comment_preset_id'])

    # 5 기본 시드 INSERT
    op.execute("""
        INSERT INTO comment_presets (name, description, is_global, is_default)
        VALUES
          ('후기형', '제품 사용 후기 + 감사 + 재확인 (3슬롯)', TRUE, TRUE),
          ('공감형', '공감 + 경험 공유 + 정보 + 격려 (4슬롯)', TRUE, TRUE),
          ('비교형', '비교 질문 + 옵션 추천 + 반박 (5슬롯)', TRUE, TRUE),
          ('정보형', '정보 제공 + 감사 + 추가 질문 (2슬롯)', TRUE, TRUE),
          ('질문형', '질문 + 답변 + 다른 시각 (3슬롯)', TRUE, TRUE);
    """)

    # 슬롯 시드 (운영자가 편집할 placeholder)
    op.execute("""
        INSERT INTO comment_tree_slots
          (comment_preset_id, slot_label, reply_to_slot_label, position, text_template)
        VALUES
          -- 후기형 (3슬롯)
          ((SELECT id FROM comment_presets WHERE name='후기형'), 'A', NULL, 1, '<후기 본문>'),
          ((SELECT id FROM comment_presets WHERE name='후기형'), 'B', 'A', 2, '감사합니다 :)'),
          ((SELECT id FROM comment_presets WHERE name='후기형'), 'C', 'B', 3, '저도 한번 써볼게요'),
          -- 공감형 (4슬롯)
          ((SELECT id FROM comment_presets WHERE name='공감형'), 'A', NULL, 1, '<공감 시작>'),
          ((SELECT id FROM comment_presets WHERE name='공감형'), 'B', 'A', 2, '<자기 경험>'),
          ((SELECT id FROM comment_presets WHERE name='공감형'), 'C', 'B', 3, '<정보 제공>'),
          ((SELECT id FROM comment_presets WHERE name='공감형'), 'D', 'A', 4, '<격려 한마디>'),
          -- 비교형 (5슬롯)
          ((SELECT id FROM comment_presets WHERE name='비교형'), 'A', NULL, 1, '<비교 질문>'),
          ((SELECT id FROM comment_presets WHERE name='비교형'), 'B', 'A', 2, '<옵션 1 추천>'),
          ((SELECT id FROM comment_presets WHERE name='비교형'), 'C', 'A', 3, '<옵션 2 추천>'),
          ((SELECT id FROM comment_presets WHERE name='비교형'), 'D', 'B', 4, '<반박 1>'),
          ((SELECT id FROM comment_presets WHERE name='비교형'), 'E', 'C', 5, '<반박 2>'),
          -- 정보형 (2슬롯)
          ((SELECT id FROM comment_presets WHERE name='정보형'), 'A', NULL, 1, '<정보 제공>'),
          ((SELECT id FROM comment_presets WHERE name='정보형'), 'B', 'A', 2, '감사합니다, 더 알려주세요'),
          -- 질문형 (3슬롯)
          ((SELECT id FROM comment_presets WHERE name='질문형'), 'A', NULL, 1, '<질문>'),
          ((SELECT id FROM comment_presets WHERE name='질문형'), 'B', 'A', 2, '<답변 시도>'),
          ((SELECT id FROM comment_presets WHERE name='질문형'), 'C', 'A', 3, '<다른 시각>');
    """)


def downgrade() -> None:
    op.drop_index('idx_niches_comment_preset', table_name='niches')
    op.drop_column('niches', 'comment_preset_id')
    op.drop_index('ix_slots_preset', table_name='comment_tree_slots')
    op.drop_table('comment_tree_slots')
    op.drop_table('comment_presets')
