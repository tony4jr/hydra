"""add workers.adspower_api_key_enc for per-worker AdsPower API key

Revision ID: f6a12b7d89e3
Revises: e8c3f9a01bd4
Create Date: 2026-04-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f6a12b7d89e3'
down_revision: Union[str, Sequence[str], None] = 'e8c3f9a01bd4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workers', sa.Column('adspower_api_key_enc', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('workers', 'adspower_api_key_enc')
