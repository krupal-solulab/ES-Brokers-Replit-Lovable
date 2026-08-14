"""merge claims-intake and broker-comm-restore branches

Revision ID: 5e41b45d6cfe
Revises: 671af1e1648a, c75384cb21f1
Create Date: 2026-08-11 17:45:52.362104
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '5e41b45d6cfe'
down_revision: Union[str, None] = ('671af1e1648a', 'c75384cb21f1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
