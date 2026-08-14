"""Pydantic request/response shapes for the Admin Panel routes (AP-01..AP-06)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TenantOut(BaseModel):
    id: str
    name: str
    vertical: str
    junior_premium_cap: float | None


class TenantUpdate(BaseModel):
    name: str | None = None
    junior_premium_cap: float | None = None


class UserOut(BaseModel):
    id: str
    email: str
    name: str | None
    role: str
    created_at: datetime


class UserCreate(BaseModel):
    email: str
    name: str | None = None
    role: str  # "junior" | "senior" | "admin"


class UserUpdate(BaseModel):
    role: str | None = None
    name: str | None = None


class SettingOut(BaseModel):
    key: str
    label: str
    description: str
    value: str
    env_default: str
    source: str  # "env_default" | "admin_override"
    updated_at: datetime | None = None
    updated_by: str | None = None


class SettingUpdate(BaseModel):
    value: str


class ConnectionSummaryOut(BaseModel):
    provider: str
    status: str


class AuditEntryOut(BaseModel):
    actor: str
    who: str
    what: str
    workflow: str
    at: datetime | None
    detail: dict[str, Any]


class OverviewOut(BaseModel):
    tenant: TenantOut
    connections: list[ConnectionSummaryOut]
    recent_audit: list[AuditEntryOut]
