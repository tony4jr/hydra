"""like_min/like_max 정규화: 거꾸로 입력된 행 swap + CHECK 제약

Revision ID: w3x4likeminmax
Revises: v1w2brndmiss
Create Date: 2026-05-07

UI에서 like_min=40, like_max=10 같이 거꾸로 저장된 케이스 발생.
근본 차단:
- 기존 (like_min > like_max) 행 swap (Python 으로 row-wise — 크로스 dialect 안전)
- Postgres CHECK 제약 추가 (like_max >= like_min, 둘 다 >= 0)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'w3x4likeminmax'
down_revision: Union[str, Sequence[str], None] = 'v1w2brndmiss'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 음수 클램프
    bind.execute(sa.text(
        "UPDATE comment_tree_slots SET like_min = 0 WHERE like_min < 0"
    ))
    bind.execute(sa.text(
        "UPDATE comment_tree_slots SET like_max = 0 WHERE like_max < 0"
    ))

    # 2) like_min > like_max 행 swap (Python row-wise — Postgres/SQLite 모두 안전)
    rows = bind.execute(sa.text(
        "SELECT id, like_min, like_max FROM comment_tree_slots WHERE like_min > like_max"
    )).fetchall()
    for row in rows:
        bind.execute(
            sa.text(
                "UPDATE comment_tree_slots SET like_min = :lo, like_max = :hi WHERE id = :id"
            ),
            {"lo": row.like_max, "hi": row.like_min, "id": row.id},
        )

    # 3) CHECK 제약 (Postgres 만 — SQLite 는 테이블 재생성 필요. 앱+alembic 레벨에서 보장)
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE comment_tree_slots "
            "ADD CONSTRAINT ck_cts_like_range "
            "CHECK (like_min >= 0 AND like_max >= like_min)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE comment_tree_slots DROP CONSTRAINT IF EXISTS ck_cts_like_range"
        )
