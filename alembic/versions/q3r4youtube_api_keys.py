"""youtube_api_keys table

Revision ID: q3r4ytkeys
Revises: o1p2brand
Create Date: 2026-05-06

YouTube Data API v3 키 풀. system_config 의 youtube_api_key / _1 / _2 를 마이그레이션.
"""
from typing import Sequence, Union
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision: str = 'q3r4ytkeys'
down_revision: Union[str, Sequence[str], None] = 'o1p2brand'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'youtube_api_keys',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('key', sa.String, nullable=False, unique=True),
        sa.Column('label', sa.String),
        sa.Column('status', sa.String, nullable=False, server_default='active'),
        sa.Column('quota_used_today', sa.Integer, nullable=False, server_default='0'),
        sa.Column('quota_limit', sa.Integer, nullable=False, server_default='10000'),
        sa.Column('last_used_at', sa.DateTime),
        sa.Column('last_reset_at', sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column('exhausted_at', sa.DateTime),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.current_timestamp()),
    )

    # system_config 의 기존 키 마이그레이션
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT key, value FROM system_config "
        "WHERE key IN ('youtube_api_key', 'youtube_api_key_1', 'youtube_api_key_2')"
    )).fetchall()
    seen = set()
    for r in rows:
        v = (r[1] or '').strip()
        if v and v not in seen:
            seen.add(v)
            bind.execute(
                sa.text(
                    "INSERT INTO youtube_api_keys (key, label, status, quota_used_today, quota_limit) "
                    "VALUES (:k, :l, 'active', 0, 10000)"
                ),
                {"k": v, "l": r[0]},
            )
    bind.execute(sa.text(
        "DELETE FROM system_config "
        "WHERE key IN ('youtube_api_key', 'youtube_api_key_1', 'youtube_api_key_2')"
    ))


def downgrade() -> None:
    op.drop_table('youtube_api_keys')
