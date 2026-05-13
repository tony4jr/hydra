"""IpLog.worker_id FK ondelete=SET NULL (Codex 5/12 P2 follow-up)

Revision ID: b1c2d3iplogsn
Revises: a1b2c3iplog
Create Date: 2026-05-13

Codex 검증: 이전 migration (a1b2c3iplog) 의 fk_ip_log_worker 가 ondelete
정책 미지정 → Postgres 기본 RESTRICT. admin_workers.delete_worker 가 IpLog
는 직접 NULL 처리하지 않아 worker 삭제 시 FK 위반으로 fail. ondelete=SET NULL
로 변경.

기존 row 영향 없음 — DDL 만 변경.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b1c2d3iplogsn"
down_revision: Union[str, Sequence[str], None] = "a1b2c3iplog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FK_NAME = "fk_ip_log_worker"


def upgrade() -> None:
    with op.batch_alter_table("ip_log") as batch:
        batch.drop_constraint(_FK_NAME, type_="foreignkey")
        batch.create_foreign_key(
            _FK_NAME, "workers", ["worker_id"], ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("ip_log") as batch:
        batch.drop_constraint(_FK_NAME, type_="foreignkey")
        batch.create_foreign_key(_FK_NAME, "workers", ["worker_id"], ["id"])
