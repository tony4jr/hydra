"""Phase 4 Slice 4.2b — terminal_chunks table

Revision ID: g5h6i7termck
Revises: f4g5h6terminp
Create Date: 2026-05-13

워커 shell process stdout/stderr chunk. (session_id, stream, seq) UNIQUE.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "g5h6i7termck"
down_revision: Union[str, Sequence[str], None] = "f4g5h6terminp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "terminal_chunks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "session_id", sa.Integer,
            sa.ForeignKey(
                "terminal_sessions.id",
                name="fk_termchunk_session",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("stream", sa.String(8), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("data", sa.Text, nullable=False),
        sa.Column("byte_size", sa.Integer, nullable=False, server_default="0"),
        sa.Column("produced_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint(
            "session_id", "stream", "seq", name="uq_termchunk_session_stream_seq",
        ),
    )
    op.create_index(
        "idx_termchunk_session_seq", "terminal_chunks", ["session_id", "seq"],
    )


def downgrade() -> None:
    op.drop_index("idx_termchunk_session_seq", table_name="terminal_chunks")
    op.drop_table("terminal_chunks")
