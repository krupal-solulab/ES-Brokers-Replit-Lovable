"""The 12 shared base tables. See package docstring for portability notes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, Column, ForeignKey, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.types import JSON, DateTime
from sqlmodel import Field, SQLModel

from core.common.enums import (
    DecisionOutcome,
    DocumentKind,
    ReviewStatus,
    Role,
    RuleStatus,
    Vertical,
)


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


def _pk() -> object:
    return Field(default_factory=_uuid, primary_key=True)


def _enum_col(enum_type: type, *, nullable: bool = False) -> object:
    """VARCHAR + CHECK-backed enum column (portable across SQLite/Postgres)."""
    return Column(SAEnum(enum_type, native_enum=False, length=32), nullable=nullable)


def _ts_col(nullable: bool = False) -> Column:
    return Column(DateTime(timezone=True), nullable=nullable)


# ── 1. Tenant ────────────────────────────────────────
class Tenant(SQLModel, table=True):
    __tablename__ = "tenant"

    id: str = _pk()
    name: str = Field(sa_column=Column(String, nullable=False))
    vertical: Vertical = Field(sa_column=_enum_col(Vertical))
    junior_premium_cap: float | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now, sa_column=_ts_col())


# ── 2. User ──────────────────────────────────────────
class User(SQLModel, table=True):
    __tablename__ = "user"

    id: str = _pk()
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    email: str = Field(sa_column=Column(String, nullable=False))
    name: str | None = None
    role: Role = Field(sa_column=_enum_col(Role))
    # Only ever set for admin-role users, via core/auth/password.py — backs
    # POST /api/core/auth/admin-login exclusively. The original email-only
    # login (POST /api/core/auth/login) never reads or requires this.
    password_hash: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    created_at: datetime = Field(default_factory=_now, sa_column=_ts_col())


# ── 3. Submission ────────────────────────────────────
class Submission(SQLModel, table=True):
    __tablename__ = "submission"

    id: str = _pk()
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    vertical: Vertical = Field(sa_column=_enum_col(Vertical))
    external_ref: str | None = None
    subject: str | None = None
    status: str = Field(default="received", sa_column=Column(String, nullable=False))
    created_at: datetime = Field(default_factory=_now, sa_column=_ts_col())


# ── 4. Document ──────────────────────────────────────
class Document(SQLModel, table=True):
    __tablename__ = "document"

    id: str = _pk()
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str = Field(
        sa_column=Column(String, ForeignKey("submission.id"), nullable=False)
    )
    kind: DocumentKind = Field(sa_column=_enum_col(DocumentKind))
    filename: str = Field(sa_column=Column(String, nullable=False))
    uri: str | None = None
    content: str | None = None
    classification_confidence: float | None = None
    created_at: datetime = Field(default_factory=_now, sa_column=_ts_col())


# ── 5. ExtractedField ────────────────────────────────
class ExtractedField(SQLModel, table=True):
    __tablename__ = "extracted_field"

    id: str = _pk()
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str = Field(
        sa_column=Column(String, ForeignKey("submission.id"), nullable=False)
    )
    document_id: str | None = Field(
        default=None, sa_column=Column(String, ForeignKey("document.id"), nullable=True)
    )
    name: str = Field(sa_column=Column(String, nullable=False))
    value: str | None = None
    confidence: float | None = None
    citation: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=_now, sa_column=_ts_col())


# ── 6. RuleSet ───────────────────────────────────────
class RuleSet(SQLModel, table=True):
    __tablename__ = "rule_set"

    id: str = _pk()
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    vertical: Vertical = Field(sa_column=_enum_col(Vertical))
    key: str = Field(sa_column=Column(String, nullable=False))  # e.g. "acord_validation"
    name: str | None = None
    active_version_id: str | None = None
    created_at: datetime = Field(default_factory=_now, sa_column=_ts_col())


# ── 7. RuleVersion (its OWN table) ───────────────────
class RuleVersion(SQLModel, table=True):
    __tablename__ = "rule_version"

    id: str = _pk()
    rule_set_id: str = Field(
        sa_column=Column(String, ForeignKey("rule_set.id"), nullable=False)
    )
    version: int = Field(default=1)
    status: RuleStatus = Field(sa_column=_enum_col(RuleStatus))
    rules: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    published_at: datetime | None = Field(default=None, sa_column=_ts_col(nullable=True))
    created_at: datetime = Field(default_factory=_now, sa_column=_ts_col())


# ── 8. Decision ──────────────────────────────────────
class Decision(SQLModel, table=True):
    __tablename__ = "decision"

    id: str = _pk()
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str = Field(
        sa_column=Column(String, ForeignKey("submission.id"), nullable=False)
    )
    outcome: DecisionOutcome = Field(sa_column=_enum_col(DecisionOutcome))
    score: float | None = None
    rationale: str | None = None
    details: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=_now, sa_column=_ts_col())


# ── 9. OutputPackage ─────────────────────────────────
class OutputPackage(SQLModel, table=True):
    __tablename__ = "output_package"

    id: str = _pk()
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str = Field(
        sa_column=Column(String, ForeignKey("submission.id"), nullable=False)
    )
    decision_id: str | None = Field(
        default=None, sa_column=Column(String, ForeignKey("decision.id"), nullable=True)
    )
    workflow: str = Field(sa_column=Column(String, nullable=False))
    payload: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=_now, sa_column=_ts_col())


# ── 10. ReviewItem ───────────────────────────────────
class ReviewItem(SQLModel, table=True):
    __tablename__ = "review_item"

    id: str = _pk()
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    submission_id: str | None = Field(
        default=None, sa_column=Column(String, ForeignKey("submission.id"), nullable=True)
    )
    output_package_id: str | None = Field(
        default=None, sa_column=Column(String, ForeignKey("output_package.id"), nullable=True)
    )
    workflow: str = Field(sa_column=Column(String, nullable=False))
    status: ReviewStatus = Field(sa_column=_enum_col(ReviewStatus))
    assigned_to: str | None = None
    created_at: datetime = Field(default_factory=_now, sa_column=_ts_col())


# ── 11. AuditEntry ───────────────────────────────────
class AuditEntry(SQLModel, table=True):
    __tablename__ = "audit_entry"

    id: str = _pk()
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    vertical: Vertical = Field(sa_column=_enum_col(Vertical))
    actor: str = Field(sa_column=Column(String, nullable=False))  # "ai" | "human"
    who: str = Field(sa_column=Column(String, nullable=False))
    what: str = Field(sa_column=Column(String, nullable=False))
    workflow: str = Field(sa_column=Column(String, nullable=False))
    detail: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    at: datetime = Field(default_factory=_now, sa_column=_ts_col())


# ── 12. Connection (Nango) ───────────────────────────
class Connection(SQLModel, table=True):
    __tablename__ = "connection"
    __table_args__ = (CheckConstraint("provider <> ''", name="ck_connection_provider"),)

    id: str = _pk()
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    provider: str = Field(sa_column=Column(String, nullable=False))  # google-mail | ...
    nango_connection_id: str | None = None
    status: str = Field(default="disconnected", sa_column=Column(String, nullable=False))
    # Target spreadsheet for the Sheets write-back fallback (provider="google-sheet"
    # only) — set by the tenant on the Integrations page once connected, shared by
    # Bind Issuance/Bordereau Reporting/Renewal Management. Unused by every other
    # provider. See docs/CONNECTORS_NANGO.md.
    sheet_id: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    # Target Drive folder for the "Upload to Drive" action (provider="google-drive"
    # only) — set by the tenant on the Integrations page once connected. Optional:
    # uploads land in the tenant's Drive root if unset. See docs/CONNECTORS_NANGO.md.
    folder_id: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    # Target Slack channel for the notification fallback (provider="slack" only)
    # — set by the tenant on the Integrations page once connected. Unused by
    # every other provider. See docs/CONNECTORS_NANGO.md.
    channel_id: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    created_at: datetime = Field(default_factory=_now, sa_column=_ts_col())


# ── 13. MonitorAlert (scheduled-monitor output — append-only, deduplicated) ───
class MonitorAlert(SQLModel, table=True):
    """Append-only alert produced by a ScheduledMonitor run.

    Resolution sets ``resolved_at``; rows are never deleted.
    ``dedupe_key`` is unique across the table — computed as
    ``"{tenant_id}:{alert_type}:{entity_ref}:{as_of_day}"`` — so re-running the
    same monitor on the same day for the same entity never creates duplicates.
    """

    __tablename__ = "monitor_alert"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_monitor_alert_dedupe_key"),
    )

    id: str = _pk()
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    vertical: Vertical = Field(sa_column=_enum_col(Vertical))
    # The workflow module that owns this alert (e.g. "binder_issuance").
    workflow: str = Field(sa_column=Column(String, nullable=False, index=True))
    # Opaque reference to the triggering entity (e.g. a bind_id or submission_id).
    entity_ref: str = Field(sa_column=Column(String, nullable=False))
    # Alert type string — per-monitor enum value (e.g. "BIND_STALE").
    alert_type: str = Field(sa_column=Column(String, nullable=False, index=True))
    # INFO | WARN | URGENT
    severity: str = Field(sa_column=Column(String, nullable=False))
    # Natural dedupe key: "{tenant_id}:{alert_type}:{entity_ref}:{as_of_day}"
    dedupe_key: str = Field(sa_column=Column(String, nullable=False, unique=True))
    # The triggering engine output — never a re-derived number (KB06).
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=_now, sa_column=_ts_col())
    # Null until dismissed; setting resolved_at is the only mutation allowed.
    resolved_at: datetime | None = Field(default=None, sa_column=_ts_col(nullable=True))
    resolved_by: str | None = Field(default=None, sa_column=Column(String, nullable=True))


# ── 14. CarrierAppetiteProfile (versioned, append-only — G2) ─────────────────
class CarrierAppetiteProfile(SQLModel, table=True):
    """Versioned carrier appetite profile.

    An "update" inserts a NEW row; old rows are never mutated or deleted.
    ``supersedes_version_id`` chains versions for a carrier.
    Latest version = MAX(created_at) per (tenant_id, carrier_id).

    ``source`` values: SEED | HUMAN_EDIT | CI_METADATA_REFRESH
    ``appetite_confidence`` values: high | medium | low
    ``gap_policy``: maps requirement_type -> "block"|"disclose" (PA-03/FR-9).
    """

    __tablename__ = "carrier_appetite_profile"

    version_id: str = _pk()
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    carrier_id: str = Field(sa_column=Column(String, nullable=False, index=True))
    carrier_name: str = Field(sa_column=Column(String, nullable=False))

    # ── Core appetite fields ──────────────────────────────────────────────────
    class_codes_accepted: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    class_codes_excluded: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    states_licensed: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    premium_band: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    submission_requirements: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    severity_ceiling: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    appetite_confidence: str = Field(sa_column=Column(String, nullable=False))
    appetite_last_updated: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    historical_hit_rate_this_class: float = Field(default=0.5)
    lines_written: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    notes: str | None = Field(default=None, sa_column=Column(String, nullable=True))

    # ── Extended fields (Package Assembly) ────────────────────────────────────
    # PA-05 proprietary form metadata (ACORD version preference, form IDs, etc.)
    form_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    # PA-03/FR-9: requirement_type -> "block" | "disclose". Empty = use default.
    gap_policy: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    # ── Versioning (KB05) ─────────────────────────────────────────────────────
    supersedes_version_id: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    created_at: datetime = Field(default_factory=_now, sa_column=_ts_col())
    created_by: str = Field(sa_column=Column(String, nullable=False))
    # SEED | HUMAN_EDIT | CI_METADATA_REFRESH
    source: str = Field(sa_column=Column(String, nullable=False))


# ── 15. PlatformSetting (Admin Panel — per-tenant override of an env tunable) ──
class PlatformSetting(SQLModel, table=True):
    __tablename__ = "platform_setting"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_platform_setting_tenant_key"),
    )

    id: str = _pk()
    tenant_id: str = Field(sa_column=Column(String, ForeignKey("tenant.id"), nullable=False))
    key: str = Field(sa_column=Column(String, nullable=False))
    value: str = Field(sa_column=Column(String, nullable=False))  # caller casts to real type
    updated_at: datetime = Field(default_factory=_now, sa_column=_ts_col())
    updated_by: str = Field(sa_column=Column(String, nullable=False))


# ── 14. JobRun (Phase 1 — Arq job tracking + queryable error queue) ──
class JobRun(SQLModel, table=True):
    __tablename__ = "job_run"

    id: str = _pk()
    tenant_id: str | None = Field(
        default=None, sa_column=Column(String, ForeignKey("tenant.id"), nullable=True)
    )
    job_name: str = Field(sa_column=Column(String, nullable=False))
    # status values: queued | running | success | error (see core.jobs.JobStatus)
    status: str = Field(default="queued", sa_column=Column(String, nullable=False, index=True))
    submission_id: str | None = None
    args: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    result: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    error: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    attempts: int = Field(default=0)
    created_at: datetime = Field(default_factory=_now, sa_column=_ts_col())
    updated_at: datetime = Field(default_factory=_now, sa_column=_ts_col())
