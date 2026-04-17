"""worker_role_columns

Revision ID: 200fbaac2ba0
Revises: 49778c080ca0
Create Date: 2026-04-17 11:21:13.731623

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '200fbaac2ba0'
down_revision: Union[str, Sequence[str], None] = '49778c080ca0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('workers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('allow_preparation', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('allow_campaign', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('workers', schema=None) as batch_op:
        batch_op.drop_column('allow_campaign')
        batch_op.drop_column('allow_preparation')
