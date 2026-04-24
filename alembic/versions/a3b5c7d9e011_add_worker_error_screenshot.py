"""add worker_errors.screenshot_url

Revision ID: a3b5c7d9e011
Revises: f6a12b7d89e3
Create Date: 2026-04-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a3b5c7d9e011'
down_revision: Union[str, Sequence[str], None] = 'f6a12b7d89e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('worker_errors', sa.Column('screenshot_url', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('worker_errors', 'screenshot_url')
