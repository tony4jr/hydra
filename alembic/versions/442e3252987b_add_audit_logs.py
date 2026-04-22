"""add_audit_logs

Revision ID: 442e3252987b
Revises: 0a5f97e5b643
Create Date: 2026-04-22 22:13:15.764192

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '442e3252987b'
down_revision: Union[str, Sequence[str], None] = '0a5f97e5b643'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """관리자 액션 감사 로그.

    기록 대상 (미들웨어/라우트에서 발생 시점에 INSERT):
    - deploy / pause / unpause / canary 변경
    - campaign/account/worker/preset 생성/수정/삭제
    - 아바타 업로드/삭제
    - 로그인/로그아웃

    metadata_json 은 JSON 으로 before/after 상태, 입력 데이터 보관.
    민감 정보 (password/token) 는 미들웨어에서 필터 후 저장.
    """
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.Integer, nullable=True),
        sa.Column("metadata_json", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),  # IPv6 최대 45자
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("timestamp", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_audit_user_time", "audit_logs", ["user_id", "timestamp"])
    op.create_index("idx_audit_action_time", "audit_logs", ["action", "timestamp"])


def downgrade() -> None:
    op.drop_index("idx_audit_action_time", "audit_logs")
    op.drop_index("idx_audit_user_time", "audit_logs")
    op.drop_table("audit_logs")
