"""brand missing columns — category + company_protected_terms

Revision ID: v1w2brndmiss
Revises: u9v0multibrand
Create Date: 2026-05-07

PR #63 Task 1 review fix 에서 Brand 모델에 추가했지만 마이그레이션 누락.
prod (Postgres) 에서 column 'brands.category' does not exist 발생.
로컬 테스트 (SQLite Base.metadata.create_all) 는 통과해서 발견 못 함.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'v1w2brndmiss'
down_revision: Union[str, Sequence[str], None] = 'u9v0multibrand'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'brands',
        sa.Column('category', sa.String(32), nullable=True),
    )
    op.add_column(
        'brands',
        sa.Column('company_protected_terms', sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column('brands', 'company_protected_terms')
    op.drop_column('brands', 'category')
