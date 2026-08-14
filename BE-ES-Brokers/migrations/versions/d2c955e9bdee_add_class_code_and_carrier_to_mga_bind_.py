"""add class_code and carrier to mga_bind_result

Revision ID: d2c955e9bdee
Revises: 5e41b45d6cfe
Create Date: 2026-08-11 17:49:11.298440
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd2c955e9bdee'
down_revision: Union[str, None] = '5e41b45d6cfe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('mga_bind_result', schema=None) as batch_op:
        batch_op.add_column(sa.Column('class_code', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('carrier', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('mga_bind_result', schema=None) as batch_op:
        batch_op.drop_column('carrier')
        batch_op.drop_column('class_code')
