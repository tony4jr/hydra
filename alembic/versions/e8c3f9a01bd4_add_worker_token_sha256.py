"""add workers.token_sha256 for O(1) auth — bcrypt 제거

Revision ID: e8c3f9a01bd4
Revises: d7a8e3b2f501
Create Date: 2026-04-24

워커 토큰은 256bit 랜덤이라 bcrypt 불필요 (brute force 불가). SHA-256 + UNIQUE
인덱스로 O(1) 조회. 잘못된 토큰이 와도 DB 0건 매칭 → 즉시 401, bcrypt 순회 안 함.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e8c3f9a01bd4'
down_revision: Union[str, Sequence[str], None] = 'd7a8e3b2f501'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workers', sa.Column('token_sha256', sa.String(length=64), nullable=True))
    op.create_index('idx_workers_token_sha256', 'workers', ['token_sha256'], unique=True)


def downgrade() -> None:
    op.drop_index('idx_workers_token_sha256', table_name='workers')
    op.drop_column('workers', 'token_sha256')
