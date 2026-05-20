"""Monthly report generation and listing."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..db import get_db
from ..deps import get_tenant_by_api_key
from ..models import Alert, LlmEvent, Report, Tenant
from ..schemas import ReportCreateRequest, ReportOut


admin_router = APIRouter(tags=["reports-admin"])
tenant_router = APIRouter(tags=["reports"])


def _parse_period(period: str) -> tuple[datetime, datetime]:
    y, m = period.split("-")
    start = datetime(int(y), int(m), 1, tzinfo=timezone.utc)
    if int(m) == 12:
        end = datetime(int(y) + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(int(y), int(m) + 1, 1, tzinfo=timezone.utc)
    return start, end


def _build_summary(db: Session, tenant: Tenant, start: datetime, end: datetime) -> dict:
    events = (
        db.query(LlmEvent)
        .filter(
            LlmEvent.tenant_id == tenant.id,
            LlmEvent.occurred_at >= start,
            LlmEvent.occurred_at < end,
        )
        .all()
    )
    n = len(events)
    if n == 0:
        return {
            "total_requests": 0,
            "error_requests": 0,
            "total_cost_jpy": "0",
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "avg_latency_ms": 0.0,
            "pii_detection_rate": 0.0,
            "by_model": {},
            "by_user_label": {},
            "alerts_count": 0,
        }

    by_model: dict[str, dict] = {}
    by_label: dict[str, dict] = {}
    total_cost = Decimal("0")
    total_lat = 0
    errors = 0
    pii_hits = 0
    for e in events:
        total_cost += e.total_cost_jpy
        total_lat += e.latency_ms
        if e.status_code >= 400:
            errors += 1
        if e.pii_detected:
            pii_hits += 1

        m_bucket = by_model.setdefault(
            e.model,
            {"requests": 0, "cost_jpy": Decimal("0"), "tokens": 0},
        )
        m_bucket["requests"] += 1
        m_bucket["cost_jpy"] += e.total_cost_jpy
        m_bucket["tokens"] += e.prompt_tokens + e.completion_tokens

        label = e.user_label or "(none)"
        l_bucket = by_label.setdefault(
            label, {"requests": 0, "cost_jpy": Decimal("0")}
        )
        l_bucket["requests"] += 1
        l_bucket["cost_jpy"] += e.total_cost_jpy

    alerts_count = (
        db.query(Alert)
        .filter(
            Alert.tenant_id == tenant.id,
            Alert.fired_at >= start,
            Alert.fired_at < end,
        )
        .count()
    )

    return {
        "total_requests": n,
        "error_requests": errors,
        "total_cost_jpy": str(total_cost),
        "total_prompt_tokens": sum(e.prompt_tokens for e in events),
        "total_completion_tokens": sum(e.completion_tokens for e in events),
        "avg_latency_ms": total_lat / n,
        "pii_detection_rate": pii_hits / n,
        "by_model": {
            k: {**v, "cost_jpy": str(v["cost_jpy"])} for k, v in by_model.items()
        },
        "by_user_label": {
            k: {**v, "cost_jpy": str(v["cost_jpy"])} for k, v in by_label.items()
        },
        "alerts_count": alerts_count,
    }


@admin_router.post(
    "/api/tenants/{tenant_id}/reports",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_report(
    tenant_id: str,
    payload: ReportCreateRequest,
    db: Session = Depends(get_db),
) -> Report:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, "tenant not found")
    start, end = _parse_period(payload.period)
    summary = _build_summary(db, tenant, start, end)

    existing = (
        db.query(Report)
        .filter(Report.tenant_id == tenant.id, Report.period == payload.period)
        .one_or_none()
    )
    if existing:
        existing.summary = summary
        existing.generated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    report = Report(tenant_id=tenant.id, period=payload.period, summary=summary)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@tenant_router.get("/api/reports", response_model=list[ReportOut])
def list_reports(
    tenant: Tenant = Depends(get_tenant_by_api_key),
    db: Session = Depends(get_db),
) -> list[Report]:
    return (
        db.query(Report)
        .filter(Report.tenant_id == tenant.id)
        .order_by(Report.period.desc())
        .all()
    )
