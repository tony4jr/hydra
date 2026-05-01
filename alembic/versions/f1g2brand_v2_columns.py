"""brand v2 columns (PR-8c)

Revision ID: f1g2brand
Revises: e5f6tags
Create Date: 2026-05-01

PR-8c — Brand 모델 7 신규 컬럼 (industry / tone / common_phrases / forbidden_words /
avoid_competitors / target_demographics).

⚠️ accounts 계열 9 테이블 미변경 (절대 원칙).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1g2brand'
down_revision: Union[str, Sequence[str], None] = 'e5f6tags'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('brands', sa.Column('industry', sa.String(60), nullable=True))
    op.add_column('brands', sa.Column('tone', sa.String(20), nullable=True))
    op.add_column('brands', sa.Column('common_phrases', sa.Text(), nullable=True))
    op.add_column('brands', sa.Column('forbidden_words', sa.Text(), nullable=True))
    op.add_column('brands', sa.Column('avoid_competitors', sa.Text(), nullable=True))
    op.add_column('brands', sa.Column('target_demographics', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('brands', 'target_demographics')
    op.drop_column('brands', 'avoid_competitors')
    op.drop_column('brands', 'forbidden_words')
    op.drop_column('brands', 'common_phrases')
    op.drop_column('brands', 'tone')
    op.drop_column('brands', 'industry')
