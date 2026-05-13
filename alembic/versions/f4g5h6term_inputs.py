"""Phase 4 Slice 4.2a — terminal_inputs table

Revision ID: f4g5h6terminp
Revises: e3f4g5termses
Create Date: 2026-05-13

운영자가 admin UI 에서 보낸 stdin 데이터 큐. 워커가 short-poll 로 가져가
shell process.stdin.write. (session_id, seq) UNIQUE.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f4g5h6terminp"
down_revision: Union[str, Sequence[str], None] = "e3f4g5termses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "terminal_inputs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "session_id", sa.Integer,
            sa.ForeignKey(
                "terminal_sessions.id",
                name="fk_terminput_session",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("data", sa.Text, nullable=False),
        sa.Column("byte_size", sa.Integer, nullable=False, server_default="0"),
        sa.Column("produced_at", sa.DateTime, nullable=False),
        sa.Column("consumed_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("session_id", "seq", name="uq_terminput_session_seq"),
    )
    op.create_index(
        "idx_terminput_session_seq", "terminal_inputs", ["session_id", "seq"],
    )


def downgrade() -> None:
    op.drop_index("idx_terminput_session_seq", table_name="terminal_inputs")
    op.drop_table("terminal_inputs")
