"""Analytics endpoints: model comparison, failover summary, user-label breakdown."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_tenant_by_api_key
from ..models import LlmEvent, Tenant
from ..schemas import (
    FailoverSummary,
    ModelCompare,
    ModelMetrics,
    UserLabelBreakdown,
    UserLabelRow,
)


router = APIRouter(tags=["analytics"])


def _model_metrics(db: Session, tenant_id: str, model: str) -> ModelMetrics:
    events = (
        db.query(LlmEvent)
        .filter(LlmEvent.tenant_id == tenant_id, LlmEvent.model == model)
        .all()
    )
    if not events:
        raise HTTPException(404, f"no events for model {model}")
    total_cost = sum((e.total_cost_jpy for e in events), Decimal("0"))
    total_lat = sum(e.latency_ms for e in events)
    errors = sum(1 for e in events if e.status_code >= 400)
    n = len(events)
    return ModelMetrics(
        model=model,
        requests=n,
        total_cost_jpy=total_cost,
        avg_cost_jpy=total_cost / n,
        avg_latency_ms=total_lat / n,
        error_rate=errors / n,
        total_prompt_tokens=sum(e.prompt_tokens for e in events),
        total_completion_tokens=sum(e.completion_tokens for e in events),
    )


@router.get("/api/models/compare", response_model=ModelCompare)
def compare_models(
    model_a: str = Query(..., min_length=1),
    model_b: str = Query(..., min_length=1),
    tenant: Tenant = Depends(get_tenant_by_api_key),
    db: Session = Depends(get_db),
) -> ModelCompare:
    a = _model_metrics(db, tenant.id, model_a)
    b = _model_metrics(db, tenant.id, model_b)

    cost_delta = (
        float(b.avg_cost_jpy - a.avg_cost_jpy) / float(a.avg_cost_jpy) * 100
        if a.avg_cost_jpy
        else 0.0
    )
    lat_delta = (
        (b.avg_latency_ms - a.avg_latency_ms) / a.avg_latency_ms * 100
        if a.avg_latency_ms
        else 0.0
    )
    return ModelCompare(a=a, b=b, cost_delta_pct=cost_delta, latency_delta_pct=lat_delta)


@router.get("/api/failovers", response_model=FailoverSummary)
def failover_summary(
    tenant: Tenant = Depends(get_tenant_by_api_key),
    db: Session = Depends(get_db),
) -> FailoverSummary:
    events = (
        db.query(LlmEvent)
        .filter(
            LlmEvent.tenant_id == tenant.id,
            LlmEvent.primary_provider.isnot(None),
        )
        .all()
    )
    actual_failovers = [e for e in events if e.primary_provider != e.provider]
    from_p: dict[str, int] = {}
    to_p: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for e in actual_failovers:
        from_p[e.primary_provider] = from_p.get(e.primary_provider, 0) + 1
        to_p[e.provider] = to_p.get(e.provider, 0) + 1
        key = e.failover_reason or "unspecified"
        reasons[key] = reasons.get(key, 0) + 1
    return FailoverSummary(
        total_failovers=len(actual_failovers),
        from_provider=from_p,
        to_provider=to_p,
        reasons=reasons,
    )


@router.get("/api/usage/by-label", response_model=UserLabelBreakdown)
def usage_by_label(
    tenant: Tenant = Depends(get_tenant_by_api_key),
    db: Session = Depends(get_db),
) -> UserLabelBreakdown:
    rows = (
        db.query(
            LlmEvent.user_label,
            func.count(LlmEvent.id),
            func.coalesce(func.sum(LlmEvent.total_cost_jpy), 0),
            func.coalesce(func.sum(LlmEvent.prompt_tokens + LlmEvent.completion_tokens), 0),
        )
        .filter(LlmEvent.tenant_id == tenant.id)
        .group_by(LlmEvent.user_label)
        .all()
    )
    items = [
        UserLabelRow(
            user_label=(lbl or "(none)"),
            requests=int(cnt),
            total_cost_jpy=Decimal(cost or 0),
            total_tokens=int(tokens or 0),
        )
        for lbl, cnt, cost, tokens in rows
    ]
    total_cost = sum((r.total_cost_jpy for r in items), Decimal("0"))
    total_req = sum(r.requests for r in items)
    return UserLabelBreakdown(
        tenant_id=tenant.id,
        items=items,
        total_cost_jpy=total_cost,
        total_requests=total_req,
    )
