"""add pipeline_stage_event table (FR-4 stage-level delay attribution)

Revision ID: f3a7d1e9c204
Revises: 2f56459f2a0d
Create Date: 2026-08-15

New table: pipeline_stage_event
  - Append-only log of when a submission entered/exited a named pipeline stage
    (e.g. "package_assembly_blocked") with an attribution field (CARRIER | BROKER | AGENT).
  - Written by workflow run_live() entry points at state transitions.
  - Used by the pipeline reporting engine to compute carrier-attributed
    time-to-placement (FR-4): elapsed time minus BROKER/AGENT-attributed spans.
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "f3a7d1e9c204"
down_revision: Union[str, None] = "6c3e8afc3e92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_stage_event",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("submission_ref", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attribution", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pipeline_stage_event", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_pipeline_stage_event_submission_ref"),
            ["submission_ref"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("pipeline_stage_event", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_pipeline_stage_event_submission_ref"))
    op.drop_table("pipeline_stage_event")
