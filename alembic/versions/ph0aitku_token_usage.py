"""Phase 0 — ai_token_usage table

Revision ID: ph0aitku
Revises: g5h6i7termck
Create Date: 2026-05-16

AI 호출별 토큰 사용량 적재. agent_name + model + I/O tokens + cache tokens + 컨텍스트(task, account).
비용 측정 및 모델 선택 결정의 데이터 기반. Phase 0 작업.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "ph0aitku"
down_revision: Union[str, Sequence[str], None] = "g5h6i7termck"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_token_usage",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("agent_name", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "task_id", sa.Integer,
            sa.ForeignKey("tasks.id", name="fk_aitku_task", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "account_id", sa.Integer,
            sa.ForeignKey("accounts.id", name="fk_aitku_account", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "occurred_at", sa.DateTime,
            nullable=False, server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("idx_aitku_time", "ai_token_usage", ["occurred_at"])
    op.create_index("idx_aitku_agent_time", "ai_token_usage", ["agent_name", "occurred_at"])


def downgrade() -> None:
    op.drop_index("idx_aitku_agent_time", table_name="ai_token_usage")
    op.drop_index("idx_aitku_time", table_name="ai_token_usage")
    op.drop_table("ai_token_usage")
