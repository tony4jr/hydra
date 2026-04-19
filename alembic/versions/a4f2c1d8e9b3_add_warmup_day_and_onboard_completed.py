"""add warmup_day and onboard_completed_at

Revision ID: a4f2c1d8e9b3
Revises: 0d6d7f124744
Create Date: 2026-04-19 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a4f2c1d8e9b3'
down_revision: Union[str, Sequence[str], None] = '0d6d7f124744'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("accounts") as batch:
        batch.add_column(sa.Column("warmup_day", sa.Integer(),
                                   nullable=False, server_default="0"))
        batch.add_column(sa.Column("onboard_completed_at", sa.DateTime(),
                                   nullable=True))

    # Backfill: WARMUP 상태인 계정을 day 1 로 설정 (진행 재개 기준점)
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE accounts SET warmup_day = 1 "
        "WHERE status = 'warmup' AND warmup_day = 0"
    ))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("accounts") as batch:
        batch.drop_column("onboard_completed_at")
        batch.drop_column("warmup_day")
