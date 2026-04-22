"""add_customer_id

Revision ID: 6517446c2698
Revises: b7e8f2c5d4a1
Create Date: 2026-04-22 20:05:06.081989

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6517446c2698'
down_revision: Union[str, Sequence[str], None] = 'b7e8f2c5d4a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """D 단계(고객 포털) 대비 customer_id nullable 컬럼 추가.

    accounts/tasks/campaigns 에 추가. Phase 1~C 에선 사용 안 함 (항상 NULL).
    multi-tenant 전환 시 기존 데이터를 특정 customer 에 귀속시키거나,
    NULL 을 '내부/시스템 소유' 로 해석.
    """
    for table in ("accounts", "tasks", "campaigns"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("customer_id", sa.Integer, nullable=True))


def downgrade() -> None:
    for table in ("accounts", "tasks", "campaigns"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("customer_id")
