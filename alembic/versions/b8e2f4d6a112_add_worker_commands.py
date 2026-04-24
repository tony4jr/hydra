"""add worker_commands table

Revision ID: b8e2f4d6a112
Revises: a3b5c7d9e011
Create Date: 2026-04-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b8e2f4d6a112'
down_revision: Union[str, Sequence[str], None] = 'a3b5c7d9e011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'worker_commands',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('worker_id', sa.Integer(), sa.ForeignKey('workers.id'), nullable=False),
        sa.Column('command', sa.String(length=64), nullable=False),
        sa.Column('payload', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('issued_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('issued_at', sa.DateTime(), nullable=False),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
    )
    op.create_index('idx_wcmd_worker_status', 'worker_commands', ['worker_id', 'status'])
    op.create_index('idx_wcmd_issued', 'worker_commands', ['issued_at'])


def downgrade() -> None:
    op.drop_index('idx_wcmd_issued', table_name='worker_commands')
    op.drop_index('idx_wcmd_worker_status', table_name='worker_commands')
    op.drop_table('worker_commands')
