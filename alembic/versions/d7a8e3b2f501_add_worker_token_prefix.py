"""add workers.token_prefix for O(1) auth lookup

Revision ID: d7a8e3b2f501
Revises: c5f1e4a9b2d0
Create Date: 2026-04-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd7a8e3b2f501'
down_revision: Union[str, Sequence[str], None] = 'c5f1e4a9b2d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workers', sa.Column('token_prefix', sa.String(length=8), nullable=True))
    op.create_index('idx_workers_token_prefix', 'workers', ['token_prefix'])
    # 기존 워커들은 token_prefix 가 null — 다음 enrollment 때 자동 채움.
    # 그 사이엔 worker_auth 가 prefix IS NULL 워커도 bcrypt 검증하도록 fallback.


def downgrade() -> None:
    op.drop_index('idx_workers_token_prefix', table_name='workers')
    op.drop_column('workers', 'token_prefix')
