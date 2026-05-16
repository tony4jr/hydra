"""Phase 1.2 — worker_errors UNKNOWN_SCREEN 컬럼 확장

Revision ID: ph1werr
Revises: ph0aitku
Create Date: 2026-05-17

5 신규 컬럼 NULL 허용 (기존 row 영향 X):
  - screen_state         (e.g. POST_PASSWORD_UNKNOWN, TRUST_DEVICE_PROMPT)
  - failure_taxonomy     (FailureTaxonomy enum value)
  - captured_html_url    (S3/local path to full HTML snapshot)
  - captured_url         (page.url at capture time)
  - captured_title       (page.title at capture time)
+ indexes: (failure_taxonomy, received_at), (screen_state, received_at)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "ph1werr"
down_revision: Union[str, Sequence[str], None] = "ph0aitku"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("worker_errors") as batch:
        batch.add_column(sa.Column("screen_state", sa.String(64), nullable=True))
        batch.add_column(sa.Column("failure_taxonomy", sa.String(32), nullable=True))
        batch.add_column(sa.Column("captured_html_url", sa.Text(), nullable=True))
        batch.add_column(sa.Column("captured_url", sa.Text(), nullable=True))
        batch.add_column(sa.Column("captured_title", sa.Text(), nullable=True))
    op.create_index(
        "idx_werr_taxonomy_time", "worker_errors",
        ["failure_taxonomy", "received_at"],
    )
    op.create_index(
        "idx_werr_state_time", "worker_errors",
        ["screen_state", "received_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_werr_state_time", table_name="worker_errors")
    op.drop_index("idx_werr_taxonomy_time", table_name="worker_errors")
    with op.batch_alter_table("worker_errors") as batch:
        batch.drop_column("captured_title")
        batch.drop_column("captured_url")
        batch.drop_column("captured_html_url")
        batch.drop_column("failure_taxonomy")
        batch.drop_column("screen_state")
