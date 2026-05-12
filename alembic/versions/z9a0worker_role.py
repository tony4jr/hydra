"""Worker Admin Agent — workers.role / parent_worker_id / capabilities

Revision ID: z9a0wkrole
Revises: y7z8wcmdlease
Create Date: 2026-05-13

Slice 2.1 — Admin Agent redesign identity 분리.
같은 물리 PC 위의 desktop_worker (브라우저 자동화) 와 admin_agent (PC 관리)
를 같은 workers 테이블에서 role 로 구분. parent_worker_id 로 연결.

기존 모든 worker row 는 backfill 단계에서 role='desktop_worker' 로 채움.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "z9a0wkrole"
down_revision: Union[str, Sequence[str], None] = "y7z8wcmdlease"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FK_PARENT_NAME = "fk_workers_parent_worker_id_workers"


def upgrade() -> None:
    # Slice 2.1 follow-up — Codex 가 SQLite batch_alter_table 모드에서
    # unnamed FK 가 'Constraint must have a name' 으로 깨지는 회귀를 잡음.
    # Column 정의에서 ForeignKey 를 빼고, batch.create_foreign_key 로 명시적
    # 이름 부여. downgrade 도 같은 이름 reference.
    with op.batch_alter_table("workers") as batch:
        batch.add_column(
            sa.Column(
                "role",
                sa.String(length=32),
                nullable=False,
                server_default="desktop_worker",
            )
        )
        batch.add_column(
            sa.Column(
                "parent_worker_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("capabilities", sa.Text(), nullable=True))
        batch.create_foreign_key(
            _FK_PARENT_NAME,
            "workers",
            ["parent_worker_id"],
            ["id"],
        )
        batch.create_index("idx_workers_role", ["role"])
        batch.create_index("idx_workers_parent", ["parent_worker_id"])


def downgrade() -> None:
    with op.batch_alter_table("workers") as batch:
        batch.drop_index("idx_workers_parent")
        batch.drop_index("idx_workers_role")
        batch.drop_constraint(_FK_PARENT_NAME, type_="foreignkey")
        batch.drop_column("capabilities")
        batch.drop_column("parent_worker_id")
        batch.drop_column("role")
