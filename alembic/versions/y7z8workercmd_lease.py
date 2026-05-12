"""add WorkerCommand lease fields

Revision ID: y7z8wcmdlease
Revises: x5y6workersess
Create Date: 2026-05-13

Slice 1 of Worker Admin Agent redesign — command lease/retry so a worker
crashing right after receiving a command does not lose the command.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'y7z8wcmdlease'
down_revision: Union[str, Sequence[str], None] = 'x5y6workersess'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('worker_commands') as batch:
        batch.add_column(sa.Column('lease_expires_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column(
            'attempt_count', sa.Integer(), nullable=False, server_default='0',
        ))
        batch.add_column(sa.Column('started_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('worker_commands') as batch:
        batch.drop_column('started_at')
        batch.drop_column('attempt_count')
        batch.drop_column('lease_expires_at')
