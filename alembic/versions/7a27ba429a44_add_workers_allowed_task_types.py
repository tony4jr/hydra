"""add workers allowed_task_types

Revision ID: 7a27ba429a44
Revises: ae5388c8ddd6
Create Date: 2026-04-23 07:58:00.000000

Task 37: 워커별 처리 가능 task_type 제한 (JSON 배열, 기본 '["*"]' wildcard).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7a27ba429a44'
down_revision: Union[str, Sequence[str], None] = 'ae5388c8ddd6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workers") as batch:
        batch.add_column(sa.Column(
            "allowed_task_types",
            sa.Text(),
            nullable=False,
            server_default='["*"]',
        ))


def downgrade() -> None:
    with op.batch_alter_table("workers") as batch:
        batch.drop_column("allowed_task_types")
