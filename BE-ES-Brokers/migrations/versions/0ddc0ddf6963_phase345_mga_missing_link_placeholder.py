"""phase345 mga missing-link placeholder

The migration file that originally produced this revision id (creating
mga_broker_comm_result / mga_endorsement_result / mga_renewal_result — phases
3-5) is missing from this repo, even though the dev DB is already stamped at
this revision and already has those tables. This placeholder exists only to
make the alembic history graph walkable again (a451a657a32d's down_revision
points here); it deliberately does not redefine those tables' DDL since they
already exist and guessing their exact columns risks a mismatch.

Revision ID: 0ddc0ddf6963
Revises: dfddb1e69297
Create Date: 2026-08-10 00:00:00.000000
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '0ddc0ddf6963'
down_revision: Union[str, None] = 'dfddb1e69297'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op — the tables this revision represents already exist in every
    real dev DB that reached this point historically."""
    pass


def downgrade() -> None:
    """No-op — see upgrade()."""
    pass
