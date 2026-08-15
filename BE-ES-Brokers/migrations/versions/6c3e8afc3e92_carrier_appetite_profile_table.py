"""carrier_appetite_profile_table

Revision ID: 6c3e8afc3e92
Revises: 712c30d18d6f
Create Date: 2026-08-15 11:32:56.236878

Hand-edited after autogenerate to remove spurious MGA-table drop/recreate
operations (same artefact as the G1 migration — Alembic's env.py sees MGA
models that don't exist in the current DB and flags them as "removed").
Only the carrier_appetite_profile table and its carrier_id index are touched.
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "6c3e8afc3e92"
down_revision: Union[str, None] = "712c30d18d6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "carrier_appetite_profile",
        sa.Column("version_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("carrier_id", sa.String(), nullable=False),
        sa.Column("carrier_name", sa.String(), nullable=False),
        sa.Column("class_codes_accepted", sa.JSON(), nullable=False),
        sa.Column("class_codes_excluded", sa.JSON(), nullable=False),
        sa.Column("states_licensed", sa.JSON(), nullable=False),
        sa.Column("premium_band", sa.JSON(), nullable=False),
        sa.Column("submission_requirements", sa.JSON(), nullable=False),
        sa.Column("severity_ceiling", sa.JSON(), nullable=False),
        sa.Column("appetite_confidence", sa.String(), nullable=False),
        sa.Column("appetite_last_updated", sa.String(), nullable=True),
        sa.Column("historical_hit_rate_this_class", sa.Float(), nullable=False),
        sa.Column("lines_written", sa.JSON(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("form_metadata", sa.JSON(), nullable=False),
        sa.Column("gap_policy", sa.JSON(), nullable=False),
        sa.Column("supersedes_version_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("version_id"),
    )
    with op.batch_alter_table("carrier_appetite_profile", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_carrier_appetite_profile_carrier_id"), ["carrier_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("carrier_appetite_profile", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_carrier_appetite_profile_carrier_id"))
    op.drop_table("carrier_appetite_profile")
