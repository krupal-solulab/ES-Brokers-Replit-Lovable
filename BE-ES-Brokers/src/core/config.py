"""Application configuration, loaded from environment / .env via pydantic-settings.

Phase 0: SQLite (aiosqlite) is the default dev database; DATABASE_URL flips to
Postgres later with no code change. Redis/Arq and real LLM/Nango wiring are Phase 1 —
their settings are declared here so the switch is config-only.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────
    app_env: str = "development"
    port: int = 4000
    document_storage_root: str = "./storage"

    # ── Database ─────────────────────────────────────
    # SQLite (async) by default. Postgres example:
    #   postgresql+asyncpg://user:pass@localhost:5432/insurance_os
    # Replit provides DATABASE_URL as postgresql:// — we normalize it to
    # postgresql+asyncpg:// and replace sslmode=disable with ssl=disable.
    database_url: str = "sqlite+aiosqlite:///./insurance_os.db"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        """Ensure async driver is used and SSL param is asyncpg-compatible."""
        if isinstance(v, str):
            # Replit injects postgresql:// — asyncpg needs postgresql+asyncpg://
            if v.startswith("postgresql://") and "+asyncpg" not in v:
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
            # asyncpg does not understand ?sslmode=... — swap for ?ssl=disable
            v = v.replace("sslmode=disable", "ssl=disable")
        return v

    # ── Redis / jobs (Arq) — Phase 1 ─────────────────
    redis_url: str = "redis://localhost:6379"

    # ── Auth (stub, Phase 0) ─────────────────────────
    # Premium ceiling a junior may approve; above this → escalate.
    junior_premium_cap: float = 150_000

    # ── LLM (OpenAI) — Phase 1 ───────────────────────
    openai_api_key: str = ""
    llm_model_fast: str = "gpt-4o-mini"
    llm_model_standard: str = "gpt-4o"
    llm_model_deep: str = "gpt-4.1"

    # ── Nango connectors — Phase 1 ───────────────────
    nango_secret_key: str = ""
    nango_host: str = "https://api.nango.dev"
    nango_integration_mail: str = "google-mail"
    nango_integration_sheet: str = "google-sheet"
    nango_integration_drive: str = "google-drive"
    nango_integration_calendar: str = "google-calendar"
    # Connect/disconnect only, like sheet/drive/calendar above — no workflow
    # reads/writes through these yet. See docs/CONNECTORS_NANGO.md.
    nango_integration_slack: str = "slack"
    nango_integration_quickbooks: str = "quickbooks"
    connectors_mode: str = "mock"  # mock = fixtures offline | live = real Nango
    # Default Gmail search for the live inbox picker — matches the real dataset's
    # "Submission - <Insured> - <Line> - Eff <date>" subject convention. Tune this
    # (e.g. drop "subject:submission", or add "from:@youragency.com") once you
    # know your real intake mailbox's conventions, no code change needed.
    nango_inbox_query: str = "in:inbox newer_than:30d subject:submission"
    # Separate query for Renewal Management's live inbox — a renewal notice's real
    # subject convention ("Renewal - <Insured> - Eff <date>", per the Workflow-02
    # dataset) doesn't contain "submission", so this workflow needs its own filter
    # rather than reusing Triage's subject:submission requirement.
    nango_renewal_inbox_query: str = "in:inbox newer_than:30d subject:renewal"
    # Separate query for Endorsement Processing's live inbox — a mid-term change
    # request's real subject convention won't contain "submission" or "renewal" either.
    nango_endorsement_inbox_query: str = "in:inbox newer_than:30d subject:endorsement"

    # ── Test data / fixtures ─────────────────────────
    test_data_root: str = ""

    # ── Quote Comparison recommendation weighting (QC-04/FR-18) ─────
    # Default price_weight=1.0/subjectivity_penalty=0.0 reproduces the
    # original pure-premium ranking exactly — configurable, not hardcoded.
    quote_rank_price_weight: float = 1.0
    quote_rank_subjectivity_penalty: float = 0.0

    # ── Carrier Appetite Intelligence signal threshold (CI-01/FR-3) ──
    # Minimum total real declinations from ONE carrier before any pattern
    # judgment fires (never off a single data point) — FR-3 explicitly
    # calls for this to be "configurable, validated during discovery,"
    # not a permanent hardcoded value. Default of 3 matches this
    # project's own verified sample-dataset scenarios.
    carrier_appetite_min_total_outcomes: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
