"""monitor_alert table

Revision ID: 712c30d18d6f
Revises: 2f56459f2a0d
Create Date: 2026-08-15 11:19:13.472532
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "712c30d18d6f"
down_revision: Union[str, None] = "2f56459f2a0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "monitor_alert",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column(
            "vertical",
            sa.Enum("MGA", "ES", name="vertical", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("workflow", sa.String(), nullable=False),
        sa.Column("entity_ref", sa.String(), nullable=False),
        sa.Column("alert_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("dedupe_key", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_monitor_alert_dedupe_key"),
    )
    with op.batch_alter_table("monitor_alert", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_monitor_alert_alert_type"), ["alert_type"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_monitor_alert_workflow"), ["workflow"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("monitor_alert", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_monitor_alert_workflow"))
        batch_op.drop_index(batch_op.f("ix_monitor_alert_alert_type"))
    op.drop_table("monitor_alert")
