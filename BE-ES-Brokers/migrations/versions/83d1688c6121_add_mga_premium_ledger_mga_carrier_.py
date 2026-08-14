"""add mga_premium_ledger, mga_carrier_profile tables, incurred_estimate column

Revision ID: 83d1688c6121
Revises: d2c955e9bdee
Create Date: 2026-08-11 18:07:27.212025
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '83d1688c6121'
down_revision: Union[str, None] = 'd2c955e9bdee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'mga_premium_ledger',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('submission_id', sa.String(), nullable=False),
        sa.Column('bind_result_id', sa.String(), nullable=False),
        sa.Column('class_code', sa.String(), nullable=True),
        sa.Column('carrier', sa.String(), nullable=True),
        sa.Column('premium', sa.Float(), nullable=False),
        sa.Column('transaction_type', sa.String(), nullable=False),
        sa.Column('effective_date', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['bind_result_id'], ['mga_bind_result.id'], ),
        sa.ForeignKeyConstraint(['submission_id'], ['submission.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('mga_premium_ledger', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_mga_premium_ledger_transaction_type'), ['transaction_type'],
            unique=False)

    op.create_table(
        'mga_carrier_profile',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('carrier_name', sa.String(), nullable=False),
        sa.Column('bordereau_types', sa.JSON(), nullable=False),
        sa.Column('frequency', sa.String(), nullable=False),
        sa.Column('due_date_rule', sa.String(), nullable=True),
        sa.Column('class_code_system', sa.String(), nullable=True),
        sa.Column('date_format', sa.String(), nullable=True),
        sa.Column('required_columns_in_order', sa.JSON(), nullable=True),
        sa.Column('historical_compilation_time_needed_days', sa.Integer(), nullable=True),
        sa.Column('accepts_carrier_statement_for_reconciliation', sa.Boolean(), nullable=False),
        sa.Column('premium_ceiling', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('mga_carrier_profile', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_mga_carrier_profile_carrier_name'), ['carrier_name'], unique=False)

    with op.batch_alter_table('mga_claims_intake_result', schema=None) as batch_op:
        batch_op.add_column(sa.Column('incurred_estimate', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('mga_claims_intake_result', schema=None) as batch_op:
        batch_op.drop_column('incurred_estimate')

    with op.batch_alter_table('mga_carrier_profile', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mga_carrier_profile_carrier_name'))
    op.drop_table('mga_carrier_profile')

    with op.batch_alter_table('mga_premium_ledger', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mga_premium_ledger_transaction_type'))
    op.drop_table('mga_premium_ledger')
