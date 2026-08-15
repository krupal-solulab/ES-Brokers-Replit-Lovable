"""add state_retention_reference table (FR-8 statutory retention lookup)

Revision ID: a2b3c4d5e6f7
Revises: f3a7d1e9c204
Create Date: 2026-08-15

New table: state_retention_reference
  - Global (no tenant_id) authoritative state → retention_period_years lookup.
  - Populated from a supplied reference file (never derived from general
    knowledge — FR-8 maximum-strictness grounding).
  - When empty: compliance engine returns retention_period_years=null for all
    states (current "never guess" behavior is fully preserved — no regression).
  - ``state`` is unique (one row per US state code); ``source_citation``
    records the statutory source; ``loaded_from`` records the filename.
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f3a7d1e9c204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "state_retention_reference",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("retention_period_years", sa.Integer(), nullable=False),
        sa.Column("source_citation", sa.String(), nullable=False),
        sa.Column("loaded_from", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state", name="uq_state_retention_reference_state"),
    )
    with op.batch_alter_table("state_retention_reference", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_state_retention_reference_state"),
            ["state"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("state_retention_reference", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_state_retention_reference_state"))
    op.drop_table("state_retention_reference")
