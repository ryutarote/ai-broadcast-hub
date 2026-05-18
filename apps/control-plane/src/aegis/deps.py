"""Reusable FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .auth import hash_key
from .db import get_db
from .models import ApiKey, Tenant


def get_tenant_by_api_key(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Tenant:
    """Resolve current tenant via `Authorization: Bearer <key>`."""
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
    if tenant is None or tenant.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant suspended or missing",
        )
    return tenant
