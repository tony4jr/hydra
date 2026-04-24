"""add_worker_errors table for remote error reporting

Revision ID: c5f1e4a9b2d0
Revises: 7a27ba429a44
Create Date: 2026-04-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5f1e4a9b2d0'
down_revision: Union[str, Sequence[str], None] = '7a27ba429a44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'worker_errors',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('worker_id', sa.Integer(), sa.ForeignKey('workers.id'), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('traceback', sa.Text(), nullable=True),
        sa.Column('context', sa.Text(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('received_at', sa.DateTime(), nullable=False),
    )
    op.create_index('idx_werr_worker_time', 'worker_errors', ['worker_id', 'received_at'])
    op.create_index('idx_werr_kind_time', 'worker_errors', ['kind', 'received_at'])


def downgrade() -> None:
    op.drop_index('idx_werr_kind_time', table_name='worker_errors')
    op.drop_index('idx_werr_worker_time', table_name='worker_errors')
    op.drop_table('worker_errors')
