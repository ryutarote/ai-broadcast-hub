"""Pydantic schemas (request/response models)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    plan: Literal["lite", "standard", "pro"] = "lite"
    contact_email: EmailStr
    daily_budget_jpy: int = 50000
    monthly_budget_jpy: int = 500000
    slack_webhook: str | None = None


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    plan: Literal["lite", "standard", "pro"] | None = None
    status: Literal["active", "suspended", "churned"] | None = None
    contact_email: EmailStr | None = None
    daily_budget_jpy: int | None = None
    monthly_budget_jpy: int | None = None
    slack_webhook: str | None = None


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    plan: str
    status: str
    contact_email: str
    daily_budget_jpy: int
    monthly_budget_jpy: int
    slack_webhook: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# API Key
# ---------------------------------------------------------------------------


class ApiKeyCreate(BaseModel):
    label: str | None = Field(default=None, max_length=100)


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    prefix: str
    label: str | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    """Returned only at creation time, contains the plaintext key."""

    plaintext_key: str


# ---------------------------------------------------------------------------
# LLM Event
# ---------------------------------------------------------------------------


class LlmEventIngest(BaseModel):
    """A simulated event posted by the LiteLLM proxy."""

    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=100)
    user_label: str | None = Field(default=None, max_length=100)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_cost_jpy: Decimal = Field(ge=0)
    latency_ms: int = Field(ge=0)
    status_code: int = 200
    error_type: str | None = None
    pii_detected: bool = False
    pii_entities: dict | None = None
    hallucination_score: float = 0.0


class LlmEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    provider: str
    model: str
    user_label: str | None
    prompt_tokens: int
    completion_tokens: int
    total_cost_jpy: Decimal
    latency_ms: int
    status_code: int
    error_type: str | None
    pii_detected: bool
    pii_entities: dict | None
    hallucination_score: float
    occurred_at: datetime


# ---------------------------------------------------------------------------
# Usage / Cost summaries
# ---------------------------------------------------------------------------


class UsageSummary(BaseModel):
    tenant_id: str
    total_requests: int
    error_requests: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cost_jpy: Decimal
    avg_latency_ms: float
    by_model: dict[str, dict]
    pii_detection_rate: float


class CostBreakdownItem(BaseModel):
    model: str
    requests: int
    cost_jpy: Decimal


class CostBreakdown(BaseModel):
    tenant_id: str
    daily_budget_jpy: int
    monthly_budget_jpy: int
    today_cost_jpy: Decimal
    month_cost_jpy: Decimal
    daily_consumption_pct: float
    monthly_consumption_pct: float
    items: list[CostBreakdownItem]


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    type: str
    severity: str
    message: str
    payload: dict | None
    fired_at: datetime
    resolved_at: datetime | None
