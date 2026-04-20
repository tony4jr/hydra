"""backfill account limits nulls

Revision ID: b7e8f2c5d4a1
Revises: a4f2c1d8e9b3
Create Date: 2026-04-20 10:00:00.000000

기존 계정 중 한도 필드가 NULL 인 row 를 기본값으로 채움. 모델 default 는
insert 타임에만 적용되므로 과거 생성된 행은 NULL 로 남아 런타임 크래시 유발.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7e8f2c5d4a1'
down_revision: Union[str, Sequence[str], None] = 'a4f2c1d8e9b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE accounts SET daily_comment_limit = 15 WHERE daily_comment_limit IS NULL"
    ))
    conn.execute(sa.text(
        "UPDATE accounts SET daily_like_limit = 50 WHERE daily_like_limit IS NULL"
    ))
    conn.execute(sa.text(
        "UPDATE accounts SET weekly_comment_limit = 70 WHERE weekly_comment_limit IS NULL"
    ))
    conn.execute(sa.text(
        "UPDATE accounts SET weekly_like_limit = 300 WHERE weekly_like_limit IS NULL"
    ))


def downgrade() -> None:
    # No-op — 백필된 값은 유지해도 무해. 굳이 되돌릴 이유 없음.
    pass
