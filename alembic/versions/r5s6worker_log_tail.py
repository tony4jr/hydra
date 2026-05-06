"""worker_log_tail + workers.verbose_mode

Revision ID: r5s6wlogtail
Revises: q3r4ytkeys
Create Date: 2026-05-06

서버 차원 워커 디버깅. INFO+ 로그를 verbose_mode 워커에서만 push.
24시간 retention (background scheduler).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'r5s6wlogtail'
down_revision: Union[str, Sequence[str], None] = 'q3r4ytkeys'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workers',
        sa.Column('verbose_mode', sa.Boolean, nullable=False, server_default=sa.text('false')),
    )

    op.create_table(
        'worker_log_tail',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('worker_id', sa.Integer, sa.ForeignKey('workers.id'), nullable=False),
        sa.Column('occurred_at', sa.DateTime, nullable=False),
        sa.Column('received_at', sa.DateTime, nullable=False,
                  server_default=sa.func.current_timestamp()),
        sa.Column('level', sa.String(16), nullable=False),
        sa.Column('logger_name', sa.String(128)),
        sa.Column('message', sa.Text, nullable=False),
    )
    op.create_index('idx_wlogtail_worker_time', 'worker_log_tail', ['worker_id', 'received_at'])
    op.create_index('idx_wlogtail_received', 'worker_log_tail', ['received_at'])


def downgrade() -> None:
    op.drop_index('idx_wlogtail_received', table_name='worker_log_tail')
    op.drop_index('idx_wlogtail_worker_time', table_name='worker_log_tail')
    op.drop_table('worker_log_tail')
    op.drop_column('workers', 'verbose_mode')
