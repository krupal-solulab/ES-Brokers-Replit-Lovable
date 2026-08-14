"""merge folder_id and channel_id branches

Revision ID: 2f56459f2a0d
Revises: 253f18aca0bb, b500fc8b9f02
Create Date: 2026-08-13 19:15:31.064427
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '2f56459f2a0d'
down_revision: Union[str, None] = ('253f18aca0bb', 'b500fc8b9f02')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
