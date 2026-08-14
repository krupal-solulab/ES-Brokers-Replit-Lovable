"""MGA-vertical tables (additive; extend the shared base, never modify it).

``mga_appetite_result`` persists the Appetite Engine's output per submission;
``mga_renewal_result`` persists the Renewal Comparison Engine's output;
``mga_broker_comm_result`` persists the Broker Communication Copilot's drafting output;
``mga_endorsement_result`` persists the Endorsement Processing engine's output, including
the MEP-05 PAS write-back record Bordereau Reporting's completeness check depends on;
``mga_quoting_result`` persists the Quoting & Rating Support engine's worksheet output;
``mga_bind_result`` persists the Bind Order & Issuance engine's output, including the
MBI-04 PAS write-back and MBI-05 issuance reconciliation status; ``mga_governance_result``
persists the Appetite Governance & Audit Trail engine's output — the aggregation layer
that reads the decision history the other tables here provide; ``mga_portfolio_result``
persists the Portfolio & Book Performance Reporting engine's output, itself an
aggregation layer over every other workflow's decision history plus Appetite
Governance's own AG-06 concentration findings; ``mga_bordereau_result`` persists the
Bordereau Reporting engine's output — per-check (completeness/format/reconciliation/
data-currency) status for each formal carrier filing; ``mga_claims_intake_result``
persists the Claims Intake Coordination engine's output — FNOL authority classification/
routing outcome for MGAs with delegated claims authority, the final workflow on the
10-workflow MGA roadmap; ``mga_premium_ledger`` persists one row per bind event (the only
premium-bearing transaction this codebase produces today), read by Portfolio Reporting's
loss-ratio/funnel aggregation and Bordereau Reporting's premium reconciliation;
``mga_carrier_profile`` is reference data (a carrier's Bordereau Requirement Profile),
not a decision log — the one table here with no ``submission_id``. Portable types only
(String/JSON/Float), same conventions as the shared base tables.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.types import JSON, DateTime, Float
from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class MgaAppetiteResult(SQLModel, table=True):
    __tablename__ = "mga_appetite_result"

    id: str = Field(default_factory=_uuid, primary_key=True)
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str = Field(
        sa_column=Column(String, ForeignKey("submission.id"), nullable=False)
    )
    outcome: str = Field(sa_column=Column(String, nullable=False, index=True))
    score: float | None = Field(default=None)
    triggered_rule_ids: list | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    flags: list | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class MgaRenewalResult(SQLModel, table=True):
    __tablename__ = "mga_renewal_result"

    id: str = Field(default_factory=_uuid, primary_key=True)
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str = Field(
        sa_column=Column(String, ForeignKey("submission.id"), nullable=False)
    )
    recommendation: str = Field(sa_column=Column(String, nullable=False, index=True))
    outcome: str = Field(sa_column=Column(String, nullable=False))
    score: float | None = Field(default=None)
    retention: str | None = Field(default=None)
    triggered_rule_ids: list | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    change_flags: list | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class MgaBrokerCommResult(SQLModel, table=True):
    __tablename__ = "mga_broker_comm_result"

    id: str = Field(default_factory=_uuid, primary_key=True)
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str = Field(
        sa_column=Column(String, ForeignKey("submission.id"), nullable=False)
    )
    source_workflow: str = Field(sa_column=Column(String, nullable=False))
    comm_type: str = Field(sa_column=Column(String, nullable=False, index=True))
    tone: str | None = Field(default=None)
    requires_compliance_review: bool = Field(default=False)
    sensitive: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class MgaEndorsementResult(SQLModel, table=True):
    __tablename__ = "mga_endorsement_result"

    id: str = Field(default_factory=_uuid, primary_key=True)
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str = Field(
        sa_column=Column(String, ForeignKey("submission.id"), nullable=False)
    )
    classification: str = Field(sa_column=Column(String, nullable=False))
    outcome: str = Field(sa_column=Column(String, nullable=False, index=True))
    premium_impact: float | None = Field(default=None)
    resulting_total_premium: float | None = Field(default=None)
    excluded_class_matched: str | None = Field(default=None)
    carrier_referral_drafted: bool = Field(default=False)
    write_back_logged: bool = Field(default=False)
    bordereau_schema_validated: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class MgaQuotingResult(SQLModel, table=True):
    __tablename__ = "mga_quoting_result"

    id: str = Field(default_factory=_uuid, primary_key=True)
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str = Field(
        sa_column=Column(String, ForeignKey("submission.id"), nullable=False)
    )
    class_code: str = Field(sa_column=Column(String, nullable=False))
    status: str = Field(sa_column=Column(String, nullable=False, index=True))
    total_indicated_premium: float | None = Field(default=None)
    benchmark_flagged: bool = Field(default=False)
    any_adjustment_capped: bool = Field(default=False)
    any_minimum_applied: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class MgaBindResult(SQLModel, table=True):
    __tablename__ = "mga_bind_result"

    id: str = Field(default_factory=_uuid, primary_key=True)
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str = Field(
        sa_column=Column(String, ForeignKey("submission.id"), nullable=False)
    )
    status: str = Field(sa_column=Column(String, nullable=False, index=True))
    authority_outcome: str | None = Field(default=None)
    write_back_logged: bool = Field(default=False)
    issuance_status: str = Field(sa_column=Column(String, nullable=False))
    issuance_discrepancy_count: int = Field(default=0)
    post_bind_obligation_count: int = Field(default=0)
    # Computed in process_from_quoting (from the finalized worksheet's class code and
    # its delegated-authority lookup) but previously discarded — persisted so a later
    # governance/concentration query can reference a bound account's class/carrier
    # without re-deriving it. Null for rows written by the fixture-driven process()
    # path, which has no worksheet/authority lookup to source them from.
    class_code: str | None = Field(default=None)
    carrier: str | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class MgaGovernanceResult(SQLModel, table=True):
    __tablename__ = "mga_governance_result"

    id: str = Field(default_factory=_uuid, primary_key=True)
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str = Field(
        sa_column=Column(String, ForeignKey("submission.id"), nullable=False)
    )
    status: str = Field(sa_column=Column(String, nullable=False, index=True))
    gap_count: int = Field(default=0)
    flagged_finding_count: int = Field(default=0)
    has_audit_report: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class MgaPortfolioResult(SQLModel, table=True):
    __tablename__ = "mga_portfolio_result"

    id: str = Field(default_factory=_uuid, primary_key=True)
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str = Field(
        sa_column=Column(String, ForeignKey("submission.id"), nullable=False)
    )
    status: str = Field(sa_column=Column(String, nullable=False, index=True))
    completeness_status: str = Field(sa_column=Column(String, nullable=False))
    gap_count: int = Field(default=0)
    has_loss_ratio: bool = Field(default=False)
    has_renewal_retention: bool = Field(default=False)
    has_appetite_exposure: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class MgaBordereauResult(SQLModel, table=True):
    __tablename__ = "mga_bordereau_result"

    id: str = Field(default_factory=_uuid, primary_key=True)
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str = Field(
        sa_column=Column(String, ForeignKey("submission.id"), nullable=False)
    )
    status: str = Field(sa_column=Column(String, nullable=False, index=True))
    bordereau_type: str = Field(sa_column=Column(String, nullable=False))
    completeness_status: str = Field(sa_column=Column(String, nullable=False))
    format_compliance_status: str = Field(sa_column=Column(String, nullable=False))
    reconciliation_status: str = Field(sa_column=Column(String, nullable=False))
    data_currency_status: str = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class MgaClaimsIntakeResult(SQLModel, table=True):
    """Rebuilt against the real Workflow-10 dataset (PRD Section 7 schema) — the CLI-01
    authority classification and routing outcome, plus CLI-07 write-back linkage
    (``carrier``, ``claim_number``) so Bordereau Reporting's future BR-06 has a real
    column to join against instead of the wholly separate fixture path it uses today."""

    __tablename__ = "mga_claims_intake_result"

    id: str = Field(default_factory=_uuid, primary_key=True)
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str = Field(
        sa_column=Column(String, ForeignKey("submission.id"), nullable=False)
    )
    authority_classification: str = Field(sa_column=Column(String, nullable=False, index=True))
    routing_outcome: str = Field(sa_column=Column(String, nullable=False))
    carrier: str | None = Field(default=None)
    claim_number: str | None = Field(default=None)
    coverage_matched: bool = Field(default=False)
    exceeds_settlement_ceiling: bool = Field(default=False)
    phi_blocked: bool = Field(default=False)
    incurred_estimate: float | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class MgaPremiumLedger(SQLModel, table=True):
    """One row per bind event — the only premium-bearing transaction this codebase
    produces today. Written exclusively by Bind & Issuance's process_from_quoting (the
    fixture-driven process() path has no worksheet/authority lookup to source these
    from, same caveat as MgaBindResult.class_code/carrier). Portfolio Reporting's
    funnel/loss-ratio aggregation and Bordereau Reporting's premium reconciliation both
    read this rather than re-deriving a premium figure from JSON payloads.

    Renewal Management never computes a re-rated premium (confirmed: RenewalDetail's
    indicated/premiumChange fields are hardcoded GAP placeholders pending a re-rate
    engine that doesn't exist yet) — so no row is ever written here at renewal time,
    only at initial bind. ``effective_date`` is nullable because Bind & Issuance's live
    worksheet-driven path doesn't yet carry a policy effective date through from
    Quoting & Rating (only the fixture-driven path's raw JSON has one) — an honest gap,
    not a placeholder."""

    __tablename__ = "mga_premium_ledger"

    id: str = Field(default_factory=_uuid, primary_key=True)
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str = Field(
        sa_column=Column(String, ForeignKey("submission.id"), nullable=False)
    )
    bind_result_id: str = Field(
        sa_column=Column(String, ForeignKey("mga_bind_result.id"), nullable=False)
    )
    class_code: str | None = Field(default=None)
    carrier: str | None = Field(default=None)
    premium: float = Field(sa_column=Column(Float, nullable=False))
    transaction_type: str = Field(
        default="NEW_BUSINESS", sa_column=Column(String, nullable=False, index=True)
    )
    effective_date: str | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class MgaCarrierProfile(SQLModel, table=True):
    """A carrier's Bordereau Requirement Profile (PRD Section 7.1) — reference data, not
    a per-submission decision log, so unlike every other table in this module it has no
    ``submission_id``. Seeded/maintained data, not computed by any engine.

    ``due_date_rule`` is schema-readiness only: BordereauEngine._timeliness_alert takes a
    pre-resolved due_date per request today rather than deriving one from a frequency +
    rule combination — nothing computes a due date from this field yet. Every other
    field is directly consumed by BordereauEngine's existing branches (format
    compliance, timeliness, reconciliation-acceptance) as-is."""

    __tablename__ = "mga_carrier_profile"

    id: str = Field(default_factory=_uuid, primary_key=True)
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    carrier_name: str = Field(sa_column=Column(String, nullable=False, index=True))
    bordereau_types: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    frequency: str = Field(sa_column=Column(String, nullable=False))
    due_date_rule: str | None = Field(default=None)
    class_code_system: str | None = Field(default=None)
    date_format: str | None = Field(default=None)
    required_columns_in_order: list | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    historical_compilation_time_needed_days: int | None = Field(default=None)
    accepts_carrier_statement_for_reconciliation: bool = Field(default=False)
    premium_ceiling: float | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
