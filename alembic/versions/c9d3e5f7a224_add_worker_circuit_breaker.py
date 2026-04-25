"""add worker circuit breaker columns

Revision ID: c9d3e5f7a224
Revises: b8e2f4d6a112
Create Date: 2026-04-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c9d3e5f7a224'
down_revision: Union[str, Sequence[str], None] = 'b8e2f4d6a112'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workers', sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('workers', sa.Column('last_failure_at', sa.DateTime(), nullable=True))
    op.add_column('workers', sa.Column('paused_reason', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('workers', 'paused_reason')
    op.drop_column('workers', 'last_failure_at')
    op.drop_column('workers', 'consecutive_failures')
