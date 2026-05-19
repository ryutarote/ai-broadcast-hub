"""CSV/JSON exports for audit (個情委対応など)."""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_tenant_by_api_key
from ..models import LlmEvent, Tenant


router = APIRouter(tags=["exports"])


EVENT_FIELDS = [
    "occurred_at",
    "model",
    "user_label",
    "pii_detected",
    "pii_entities",
    "provider",
    "primary_provider",
    "failover_reason",
    "prompt_tokens",
    "completion_tokens",
    "total_cost_jpy",
    "latency_ms",
    "status_code",
    "error_type",
]


@router.get("/api/exports/events")
def export_events(
    format: str = Query("csv", pattern="^(csv|json)$"),
    tenant: Tenant = Depends(get_tenant_by_api_key),
    db: Session = Depends(get_db),
) -> Response:
    events = (
        db.query(LlmEvent)
        .filter(LlmEvent.tenant_id == tenant.id)
        .order_by(LlmEvent.occurred_at.asc())
        .all()
    )
    rows = []
    for e in events:
        rows.append(
            {
                "occurred_at": e.occurred_at.isoformat(),
                "model": e.model,
                "user_label": e.user_label or "",
                "pii_detected": e.pii_detected,
                "pii_entities": json.dumps(e.pii_entities, ensure_ascii=False)
                if e.pii_entities
                else "",
                "provider": e.provider,
                "primary_provider": e.primary_provider or "",
                "failover_reason": e.failover_reason or "",
                "prompt_tokens": e.prompt_tokens,
                "completion_tokens": e.completion_tokens,
                "total_cost_jpy": str(e.total_cost_jpy),
                "latency_ms": e.latency_ms,
                "status_code": e.status_code,
                "error_type": e.error_type or "",
            }
        )

    if format == "json":
        return Response(
            content=json.dumps(rows, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="aegis-events-{tenant.id}.json"'
            },
        )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=EVENT_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="aegis-events-{tenant.id}.csv"'
        },
    )
