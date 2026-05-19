"""Tenant deletion with cryptographic certificate."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..db import get_db
from ..models import Alert, ApiKey, LlmEvent, Report, Tenant
from ..schemas import DeletionCertificate, DeletionRequest


router = APIRouter(tags=["deletion"])


@router.post(
    "/api/tenants/{tenant_id}/deletion",
    response_model=DeletionCertificate,
    dependencies=[Depends(require_admin)],
)
def delete_tenant_with_certificate(
    tenant_id: str,
    payload: DeletionRequest,
    db: Session = Depends(get_db),
) -> DeletionCertificate:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, "tenant not found")

    if payload.confirm_name != tenant.name:
        raise HTTPException(
            400,
            f"confirm_name mismatch: expected '{tenant.name}'",
        )

    events_deleted = (
        db.query(LlmEvent).filter(LlmEvent.tenant_id == tenant_id).count()
    )
    keys_deleted = db.query(ApiKey).filter(ApiKey.tenant_id == tenant_id).count()
    alerts_deleted = db.query(Alert).filter(Alert.tenant_id == tenant_id).count()
    reports_deleted = db.query(Report).filter(Report.tenant_id == tenant_id).count()

    deleted_at = datetime.now(timezone.utc)
    cert_input = (
        f"{tenant.id}|{tenant.name}|events={events_deleted}|keys={keys_deleted}|"
        f"alerts={alerts_deleted}|reports={reports_deleted}|"
        f"reason={payload.reason}|deleted_at={deleted_at.isoformat()}"
    )
    sha256 = hashlib.sha256(cert_input.encode("utf-8")).hexdigest()

    # CASCADE delete via FK on child rows (configured ondelete="CASCADE")
    db.delete(tenant)
    db.commit()

    return DeletionCertificate(
        tenant_id=tenant_id,
        tenant_name=tenant.name,
        events_deleted=events_deleted,
        api_keys_deleted=keys_deleted,
        alerts_deleted=alerts_deleted,
        reports_deleted=reports_deleted,
        reason=payload.reason,
        deleted_at=deleted_at,
        sha256=sha256,
    )
