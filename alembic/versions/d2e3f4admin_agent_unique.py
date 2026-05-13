"""workers: partial unique index for admin_agent 1:1 enforcement

Revision ID: d2e3f4adunq
Revises: c1d2e3wcmdtr
Create Date: 2026-05-13

Slice 3.2 Codex follow-up — admin_agent : desktop_worker 1:1 강제를
앱 레벨 SELECT first() 만으로는 race 시 깨질 수 있음. partial unique
index 로 DB 가 보장.

WHERE role='admin_agent' AND parent_worker_id IS NOT NULL UNIQUE (parent_worker_id)

Postgres + SQLite 둘 다 partial index 지원.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d2e3f4adunq"
down_revision: Union[str, Sequence[str], None] = "c1d2e3wcmdtr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_IDX_NAME = "uq_workers_admin_agent_parent"
_WHERE = "role = 'admin_agent' AND parent_worker_id IS NOT NULL"


def upgrade() -> None:
    op.create_index(
        _IDX_NAME,
        "workers",
        ["parent_worker_id"],
        unique=True,
        postgresql_where=sa.text(_WHERE),
        sqlite_where=sa.text(_WHERE),
    )


def downgrade() -> None:
    op.drop_index(_IDX_NAME, table_name="workers")
