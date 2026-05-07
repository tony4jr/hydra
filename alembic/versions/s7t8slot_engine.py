"""slot engine — slot reappearance + task slot link

Revision ID: s7t8slotengine
Revises: r5s6wlogtail
Create Date: 2026-05-06

PR-8d/8e 댓글 트리 프리셋을 실행 엔진에 연결.

1. comment_tree_slots.same_account_as_slot_label
   같은 프리셋 안에서 "이 슬롯은 라벨 X 슬롯과 동일 계정으로 실행" 강제.
   F5 흐름의 D=B 같은 자기 답글 패턴을 표현.

2. tasks.slot_id / tasks.slot_label / tasks.parent_task_id
   슬롯 트리 → 태스크 변환 결과 추적. parent_task_id 로 답글 체인 정합성 보장.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 's7t8slotengine'
down_revision: Union[str, Sequence[str], None] = 'r5s6wlogtail'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 슬롯 재등장 표현
    op.add_column(
        'comment_tree_slots',
        sa.Column('same_account_as_slot_label', sa.String(4), nullable=True),
    )

    # 2) 태스크 ↔ 슬롯 연결
    op.add_column(
        'tasks',
        sa.Column('slot_id', sa.Integer,
                  sa.ForeignKey('comment_tree_slots.id', ondelete='SET NULL'),
                  nullable=True),
    )
    op.add_column(
        'tasks',
        sa.Column('slot_label', sa.String(4), nullable=True),
    )
    op.add_column(
        'tasks',
        sa.Column('parent_task_id', sa.Integer,
                  sa.ForeignKey('tasks.id', ondelete='SET NULL'),
                  nullable=True),
    )

    op.create_index('idx_tasks_slot', 'tasks', ['slot_id'])
    op.create_index('idx_tasks_parent', 'tasks', ['parent_task_id'])

    # 3) 캠페인 ↔ 댓글 프리셋 직접 연결 (Niche 우회 외 다이렉트 매핑 허용)
    op.add_column(
        'campaigns',
        sa.Column('comment_preset_id', sa.Integer,
                  sa.ForeignKey('comment_presets.id', ondelete='SET NULL'),
                  nullable=True),
    )


def downgrade() -> None:
    op.drop_column('campaigns', 'comment_preset_id')
    op.drop_index('idx_tasks_parent', table_name='tasks')
    op.drop_index('idx_tasks_slot', table_name='tasks')
    op.drop_column('tasks', 'parent_task_id')
    op.drop_column('tasks', 'slot_label')
    op.drop_column('tasks', 'slot_id')
    op.drop_column('comment_tree_slots', 'same_account_as_slot_label')
