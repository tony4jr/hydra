"""brand product_name column

Revision ID: o1p2brand
Revises: m9n0fav
Create Date: 2026-05-03

브랜드의 상품명 분리. 운영 모델: 회사 = brand.name, 상품 = brand.product_name.
예) 트리코라(name) — 모렉신(product_name) — 탈모영양제(product_category).

⚠️ accounts 9 테이블 미변경.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'o1p2brand'
down_revision: Union[str, Sequence[str], None] = 'm9n0fav'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('brands', sa.Column('product_name', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('brands', 'product_name')
