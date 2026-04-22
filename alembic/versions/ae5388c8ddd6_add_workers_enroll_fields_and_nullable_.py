"""add workers enroll fields and nullable token_hash

Revision ID: ae5388c8ddd6
Revises: 11fae880a5dd
Create Date: 2026-04-23 07:08:08.817641

Task 20 — enrollment 플로우 지원:
- token_hash NOT NULL → NULL 허용 (enrollment 전 등록 가능)
- enrolled_at (DateTime) : enrollment 시점
- health_snapshot (Text JSON) : heartbeat 마지막 상태
- tailscale_ip (String 45) : 선택 (VPN IP)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ae5388c8ddd6'
down_revision: Union[str, Sequence[str], None] = '11fae880a5dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workers") as batch:
        batch.alter_column("token_hash", existing_type=sa.String(), nullable=True)
        batch.add_column(sa.Column("enrolled_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("health_snapshot", sa.Text(), nullable=True))
        batch.add_column(sa.Column("tailscale_ip", sa.String(length=45), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workers") as batch:
        batch.drop_column("tailscale_ip")
        batch.drop_column("health_snapshot")
        batch.drop_column("enrolled_at")
        batch.alter_column("token_hash", existing_type=sa.String(), nullable=False)
