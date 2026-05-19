"""Reusable FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .auth import hash_key
from .db import get_db
from .models import ApiKey, Tenant


def _resolve_tenant(
    authorization: str | None,
    db: Session,
    *,
    allowed_statuses: set[str],
) -> Tenant:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="empty bearer token",
        )
    key_hash = hash_key(token)
    api_key = (
        db.query(ApiKey)
        .filter(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
        .one_or_none()
    )
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid api key",
        )
    tenant = db.get(Tenant, api_key.tenant_id)
    if tenant is None or tenant.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"tenant not available (status={tenant.status if tenant else 'missing'})",
        )
    return tenant


def get_tenant_by_api_key(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Tenant:
    """Resolve tenant (active only). Default for read & write endpoints."""
    return _resolve_tenant(authorization, db, allowed_statuses={"active"})


# Backwards-compat alias for endpoints that explicitly require active.
get_active_tenant_by_api_key = get_tenant_by_api_key


def get_tenant_by_api_key_incl_suspended(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Tenant:
    """Allow active + suspended (used for alerts so suspended tenants can read why)."""
    return _resolve_tenant(
        authorization, db, allowed_statuses={"active", "suspended"}
    )
