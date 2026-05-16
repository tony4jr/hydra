"""Phase 3.1 — screen_resolutions table (UNKNOWN labels → auto handle)

Revision ID: ph3sresol
Revises: ph1werr
Create Date: 2026-05-17

UNKNOWN_SCREEN 캡처본을 운영자가 분류 → 동일 화면 다시 등장 시 자동 처리.
학습 루프의 핵심 조각.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "ph3sresol"
down_revision: Union[str, Sequence[str], None] = "ph1werr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "screen_resolutions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("screen_state", sa.String(64), nullable=False),
        sa.Column("url_pattern", sa.Text, nullable=True),     # substring match
        sa.Column("title_pattern", sa.Text, nullable=True),    # substring match
        sa.Column("dom_signature", sa.String(128), nullable=True),  # hash of structural fingerprint
        sa.Column("resolution_type", sa.String(32), nullable=False),
        # 'auto_click_skip' / 'auto_enter_code' / 'escalate_manual' / 'fail_task' / 'retry_after_cooldown'
        sa.Column("action_config", sa.Text, nullable=True),    # JSON: selector/text/wait_sec/etc.
        sa.Column("source_error_id", sa.Integer,
                  sa.ForeignKey("worker_errors.id", name="fk_sres_source", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_by_user_id", sa.Integer, nullable=True),  # admin user (no FK yet)
        sa.Column("approved", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("hit_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_hit_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("idx_sres_state", "screen_resolutions", ["screen_state"])
    op.create_index("idx_sres_signature", "screen_resolutions", ["dom_signature"])
    op.create_index("idx_sres_approved", "screen_resolutions", ["approved", "screen_state"])


def downgrade() -> None:
    op.drop_index("idx_sres_approved", table_name="screen_resolutions")
    op.drop_index("idx_sres_signature", table_name="screen_resolutions")
    op.drop_index("idx_sres_state", table_name="screen_resolutions")
    op.drop_table("screen_resolutions")
