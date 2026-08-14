"""rebuild mga_claims_intake_result for real Workflow-10 schema

Revision ID: 18538cf69e48
Revises: 83d1688c6121
Create Date: 2026-08-11 18:46:42.633029
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '18538cf69e48'
down_revision: Union[str, None] = '83d1688c6121'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The old table only ever held speculative dev-fixture rows from a pre-dataset
    # engine design (severity/routing/acknowledgment_status fields whose values don't
    # correspond to the real Workflow-10 PRD schema) — dropping and recreating rather
    # than migrating data that was never real to begin with.
    op.drop_table('mga_claims_intake_result')
    op.create_table(
        'mga_claims_intake_result',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('submission_id', sa.String(), nullable=False),
        sa.Column('authority_classification', sa.String(), nullable=False),
        sa.Column('routing_outcome', sa.String(), nullable=False),
        sa.Column('carrier', sa.String(), nullable=True),
        sa.Column('claim_number', sa.String(), nullable=True),
        sa.Column('coverage_matched', sa.Boolean(), nullable=False),
        sa.Column('exceeds_settlement_ceiling', sa.Boolean(), nullable=False),
        sa.Column('phi_blocked', sa.Boolean(), nullable=False),
        sa.Column('incurred_estimate', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['submission_id'], ['submission.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('mga_claims_intake_result', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_mga_claims_intake_result_authority_classification'),
            ['authority_classification'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('mga_claims_intake_result', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mga_claims_intake_result_authority_classification'))
    op.drop_table('mga_claims_intake_result')
    op.create_table(
        'mga_claims_intake_result',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('submission_id', sa.String(), nullable=False),
        sa.Column('severity', sa.String(), nullable=False),
        sa.Column('routing', sa.String(), nullable=False),
        sa.Column('coverage_matched', sa.Boolean(), nullable=False),
        sa.Column('exceeds_settlement_ceiling', sa.Boolean(), nullable=False),
        sa.Column('acknowledgment_status', sa.String(), nullable=False),
        sa.Column('incurred_estimate', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['submission_id'], ['submission.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('mga_claims_intake_result', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_mga_claims_intake_result_routing'), ['routing'], unique=False)
