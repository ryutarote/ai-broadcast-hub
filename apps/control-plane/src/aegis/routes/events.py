"""LLM event ingestion + usage/cost summaries + alert generation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..deps import get_tenant_by_api_key
from ..db import get_db
from ..models import Alert, LlmEvent, Tenant
from ..schemas import (
    AlertOut,
    CostBreakdown,
    CostBreakdownItem,
    LlmEventIngest,
    LlmEventOut,
    UsageSummary,
)


router = APIRouter(tags=["events"])


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


@router.post(
    "/api/events",
    response_model=LlmEventOut,
    status_code=status.HTTP_201_CREATED,
)
def ingest_event(
    payload: LlmEventIngest,
    tenant: Tenant = Depends(get_tenant_by_api_key),
    db: Session = Depends(get_db),
) -> LlmEvent:
    event = LlmEvent(
        tenant_id=tenant.id,
        provider=payload.provider,
        model=payload.model,
        user_label=payload.user_label,
        prompt_tokens=payload.prompt_tokens,
        completion_tokens=payload.completion_tokens,
        total_cost_jpy=payload.total_cost_jpy,
        latency_ms=payload.latency_ms,
        status_code=payload.status_code,
        error_type=payload.error_type,
        pii_detected=payload.pii_detected,
        pii_entities=payload.pii_entities,
        hallucination_score=payload.hallucination_score,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    _evaluate_alerts(db, tenant, event)
    return event


# ---------------------------------------------------------------------------
# Usage summary
# ---------------------------------------------------------------------------


@router.get("/api/usage", response_model=UsageSummary)
def usage_summary(
    tenant: Tenant = Depends(get_tenant_by_api_key),
    db: Session = Depends(get_db),
) -> UsageSummary:
    events = db.query(LlmEvent).filter(LlmEvent.tenant_id == tenant.id).all()
    if not events:
        return UsageSummary(
            tenant_id=tenant.id,
            total_requests=0,
            error_requests=0,
            total_prompt_tokens=0,
            total_completion_tokens=0,
            total_cost_jpy=Decimal("0"),
            avg_latency_ms=0.0,
            by_model={},
            pii_detection_rate=0.0,
        )

    total_cost = sum((e.total_cost_jpy for e in events), Decimal("0"))
    total_latency = sum(e.latency_ms for e in events)
    pii_hits = sum(1 for e in events if e.pii_detected)
    errors = sum(1 for e in events if e.status_code >= 400)

    by_model: dict[str, dict] = {}
    for e in events:
        bucket = by_model.setdefault(
            e.model,
            {"requests": 0, "cost_jpy": Decimal("0"), "tokens": 0},
        )
        bucket["requests"] += 1
        bucket["cost_jpy"] = bucket["cost_jpy"] + e.total_cost_jpy
        bucket["tokens"] += e.prompt_tokens + e.completion_tokens

    return UsageSummary(
        tenant_id=tenant.id,
        total_requests=len(events),
        error_requests=errors,
        total_prompt_tokens=sum(e.prompt_tokens for e in events),
        total_completion_tokens=sum(e.completion_tokens for e in events),
        total_cost_jpy=total_cost,
        avg_latency_ms=total_latency / len(events) if events else 0.0,
        by_model=by_model,
        pii_detection_rate=pii_hits / len(events) if events else 0.0,
    )


# ---------------------------------------------------------------------------
# Cost breakdown
# ---------------------------------------------------------------------------


@router.get("/api/costs", response_model=CostBreakdown)
def cost_breakdown(
    tenant: Tenant = Depends(get_tenant_by_api_key),
    db: Session = Depends(get_db),
) -> CostBreakdown:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    today_cost = (
        db.query(func.coalesce(func.sum(LlmEvent.total_cost_jpy), 0))
        .filter(
            LlmEvent.tenant_id == tenant.id,
            LlmEvent.occurred_at >= today_start,
        )
        .scalar()
    )
    month_cost = (
        db.query(func.coalesce(func.sum(LlmEvent.total_cost_jpy), 0))
        .filter(
            LlmEvent.tenant_id == tenant.id,
            LlmEvent.occurred_at >= month_start,
        )
        .scalar()
    )
    today_cost = Decimal(today_cost or 0)
    month_cost = Decimal(month_cost or 0)

    rows = (
        db.query(
            LlmEvent.model,
            func.count(LlmEvent.id),
            func.coalesce(func.sum(LlmEvent.total_cost_jpy), 0),
        )
        .filter(
            LlmEvent.tenant_id == tenant.id,
            LlmEvent.occurred_at >= month_start,
        )
        .group_by(LlmEvent.model)
        .all()
    )

    items = [
        CostBreakdownItem(model=m, requests=int(c), cost_jpy=Decimal(s or 0))
        for m, c, s in rows
    ]

    daily_pct = (
        float(today_cost) / tenant.daily_budget_jpy * 100
        if tenant.daily_budget_jpy
        else 0.0
    )
    monthly_pct = (
        float(month_cost) / tenant.monthly_budget_jpy * 100
        if tenant.monthly_budget_jpy
        else 0.0
    )

    return CostBreakdown(
        tenant_id=tenant.id,
        daily_budget_jpy=tenant.daily_budget_jpy,
        monthly_budget_jpy=tenant.monthly_budget_jpy,
        today_cost_jpy=today_cost,
        month_cost_jpy=month_cost,
        daily_consumption_pct=round(daily_pct, 2),
        monthly_consumption_pct=round(monthly_pct, 2),
        items=items,
    )


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


@router.get("/api/alerts", response_model=list[AlertOut])
def list_alerts(
    tenant: Tenant = Depends(get_tenant_by_api_key),
    db: Session = Depends(get_db),
) -> list[Alert]:
    return (
        db.query(Alert)
        .filter(Alert.tenant_id == tenant.id)
        .order_by(Alert.fired_at.desc())
        .limit(100)
        .all()
    )


# ---------------------------------------------------------------------------
# Alert evaluation (synchronous, called after each ingest for MVP)
# ---------------------------------------------------------------------------


def _evaluate_alerts(db: Session, tenant: Tenant, event: LlmEvent) -> None:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 1) PII detection alert
    if event.pii_detected:
        _maybe_fire(
            db,
            tenant,
            type_="pii_detected",
            severity="warn",
            message=f"PII detected in request: {list((event.pii_entities or {}).keys())}",
            payload={"event_id": event.id, "entities": event.pii_entities},
        )

    # 2) Daily budget thresholds
    today_cost = Decimal(
        db.query(func.coalesce(func.sum(LlmEvent.total_cost_jpy), 0))
        .filter(
            LlmEvent.tenant_id == tenant.id,
            LlmEvent.occurred_at >= today_start,
        )
        .scalar()
        or 0
    )
    if tenant.daily_budget_jpy:
        pct = float(today_cost) / tenant.daily_budget_jpy * 100
        if pct >= 100:
            _maybe_fire(
                db,
                tenant,
                type_="cost_threshold_100",
                severity="critical",
                message=f"Daily budget exceeded: ¥{today_cost:.0f} / ¥{tenant.daily_budget_jpy}",
                payload={"pct": pct},
            )
        elif pct >= 80:
            _maybe_fire(
                db,
                tenant,
                type_="cost_threshold_80",
                severity="warn",
                message=f"Daily budget 80% reached: ¥{today_cost:.0f} / ¥{tenant.daily_budget_jpy}",
                payload={"pct": pct},
            )

    # 3) Error rate
    if event.status_code >= 500:
        _maybe_fire(
            db,
            tenant,
            type_="provider_5xx",
            severity="warn",
            message=f"Provider returned {event.status_code} ({event.error_type})",
            payload={"event_id": event.id},
        )


def _maybe_fire(
    db: Session,
    tenant: Tenant,
    *,
    type_: str,
    severity: str,
    message: str,
    payload: dict | None,
) -> None:
    """Avoid duplicate alerts of the same type in the past hour."""
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    exists = (
        db.query(Alert)
        .filter(
            Alert.tenant_id == tenant.id,
            Alert.type == type_,
            Alert.fired_at >= one_hour_ago,
            Alert.resolved_at.is_(None),
        )
        .first()
    )
    if exists is not None:
        return
    alert = Alert(
        tenant_id=tenant.id,
        type=type_,
        severity=severity,
        message=message,
        payload=payload,
    )
    db.add(alert)
    db.commit()
