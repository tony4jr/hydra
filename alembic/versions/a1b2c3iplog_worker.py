"""Add IpLog.worker_id for end-ownership verification

Revision ID: a1b2c3iplog
Revises: z9a0wkrole
Create Date: 2026-05-13

Codex 5/12 P2 — /ip-log/end 가 log_id 만 알면 어떤 worker 든 ended 처리 가능
하던 결함 fix. 같은 PC 의 worker 가 다른 worker 의 IpLog 를 닫지 못하도록
worker_id 컬럼 추가 + end 시 verify.

nullable + index. 기존 row 는 backfill 없이 NULL — end 시 NULL 인 경우는
soft skip (옛 데이터 호환).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a1b2c3iplog"
down_revision: Union[str, Sequence[str], None] = "z9a0wkrole"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FK_NAME = "fk_ip_log_worker"


def upgrade() -> None:
    with op.batch_alter_table("ip_log") as batch:
        batch.add_column(sa.Column("worker_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(_FK_NAME, "workers", ["worker_id"], ["id"])
        batch.create_index("idx_ip_worker", ["worker_id"])


def downgrade() -> None:
    with op.batch_alter_table("ip_log") as batch:
        batch.drop_index("idx_ip_worker")
        batch.drop_constraint(_FK_NAME, type_="foreignkey")
        batch.drop_column("worker_id")
