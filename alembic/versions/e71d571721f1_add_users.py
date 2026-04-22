"""add_users

Revision ID: e71d571721f1
Revises: 6517446c2698
Create Date: 2026-04-22 22:02:25.286423

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e71d571721f1'
down_revision: Union[str, Sequence[str], None] = '6517446c2698'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """어드민 로그인용 users 테이블 생성.

    역할:
    - admin     : 전체 권한 (배포/정지/계정 관리)
    - operator  : 일상 운영 (태스크 승인, 캠페인 관리)
    - customer  : D 단계 대비 (외부 고객 포털 — Phase 1 에선 미사용)
    """
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="operator"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime, nullable=True),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("idx_users_email", "users")
    op.drop_table("users")
