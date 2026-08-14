"""restore missing mga_broker_comm_result / mga_endorsement_result / mga_renewal_result

The migration that should have created these three tables (phases 3-5) was
lost from the repo — see 0ddc0ddf6963's docstring. Every existing SQLite dev
DB already has them (created outside Alembic), so that revision is a no-op.
A brand-new database (e.g. this project's new Postgres target) would
otherwise never get them. This migration creates them for real, matching the
live SQLite columns exactly (verified via PRAGMA table_info against the
current dev DB) and the current SQLModel definitions in
verticals/mga/models.py.

Revision ID: c75384cb21f1
Revises: 73612dbed000
Create Date: 2026-08-11 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c75384cb21f1'
down_revision: Union[str, None] = '73612dbed000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('mga_renewal_result',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('tenant_id', sa.String(), nullable=False),
    sa.Column('submission_id', sa.String(), nullable=False),
    sa.Column('recommendation', sa.String(), nullable=False),
    sa.Column('outcome', sa.String(), nullable=False),
    sa.Column('score', sa.Float(), nullable=True),
    sa.Column('retention', sa.String(), nullable=True),
    sa.Column('triggered_rule_ids', sa.JSON(), nullable=True),
    sa.Column('change_flags', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['submission_id'], ['submission.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mga_renewal_result', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mga_renewal_result_recommendation'), ['recommendation'], unique=False)

    op.create_table('mga_broker_comm_result',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('tenant_id', sa.String(), nullable=False),
    sa.Column('submission_id', sa.String(), nullable=False),
    sa.Column('source_workflow', sa.String(), nullable=False),
    sa.Column('comm_type', sa.String(), nullable=False),
    sa.Column('tone', sa.String(), nullable=True),
    sa.Column('requires_compliance_review', sa.Boolean(), nullable=False),
    sa.Column('sensitive', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['submission_id'], ['submission.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mga_broker_comm_result', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mga_broker_comm_result_comm_type'), ['comm_type'], unique=False)

    op.create_table('mga_endorsement_result',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('tenant_id', sa.String(), nullable=False),
    sa.Column('submission_id', sa.String(), nullable=False),
    sa.Column('classification', sa.String(), nullable=False),
    sa.Column('outcome', sa.String(), nullable=False),
    sa.Column('premium_impact', sa.Float(), nullable=True),
    sa.Column('resulting_total_premium', sa.Float(), nullable=True),
    sa.Column('excluded_class_matched', sa.String(), nullable=True),
    sa.Column('carrier_referral_drafted', sa.Boolean(), nullable=False),
    sa.Column('write_back_logged', sa.Boolean(), nullable=False),
    sa.Column('bordereau_schema_validated', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['submission_id'], ['submission.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mga_endorsement_result', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mga_endorsement_result_outcome'), ['outcome'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('mga_endorsement_result', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mga_endorsement_result_outcome'))
    op.drop_table('mga_endorsement_result')

    with op.batch_alter_table('mga_broker_comm_result', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mga_broker_comm_result_comm_type'))
    op.drop_table('mga_broker_comm_result')

    with op.batch_alter_table('mga_renewal_result', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mga_renewal_result_recommendation'))
    op.drop_table('mga_renewal_result')
