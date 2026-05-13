"""WorkerCommand.target_role — Phase 3 Slice 3.1

Revision ID: c1d2e3wcmdtr
Revises: b1c2d3iplogsn
Create Date: 2026-05-13

Phase 3 — admin POST /command 에 target_role 인자 추가 + heartbeat lease 시
worker.role 검증. NULL 허용 (backward compat — 기존 pending 명령은 role
체크 안 함).

기존 row 영향 없음 — 새 컬럼만 추가.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c1d2e3wcmdtr"
down_revision: Union[str, Sequence[str], None] = "b1c2d3iplogsn"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("worker_commands") as batch:
        batch.add_column(
            sa.Column("target_role", sa.String(length=32), nullable=True),
        )
        batch.create_index("idx_wcmd_target_role", ["target_role"])


def downgrade() -> None:
    with op.batch_alter_table("worker_commands") as batch:
        batch.drop_index("idx_wcmd_target_role")
        batch.drop_column("target_role")
