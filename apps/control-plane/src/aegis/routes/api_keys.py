"""API key management."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import generate_api_key, require_admin
from ..db import get_db
from ..models import ApiKey, Tenant
from ..schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut

router = APIRouter(prefix="/api/tenants/{tenant_id}/api-keys", tags=["api-keys"])


@router.post(
    "",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_api_key(
    tenant_id: str, payload: ApiKeyCreate, db: Session = Depends(get_db)
) -> ApiKeyCreated:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant not found")

    prefix, plaintext, key_hash = generate_api_key()
    api_key = ApiKey(
        tenant_id=tenant.id,
        prefix=prefix,
        key_hash=key_hash,
        label=payload.label,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return ApiKeyCreated(
        id=api_key.id,
        tenant_id=api_key.tenant_id,
        prefix=api_key.prefix,
        label=api_key.label,
        revoked_at=api_key.revoked_at,
        created_at=api_key.created_at,
        plaintext_key=plaintext,
    )


@router.get(
    "",
    response_model=list[ApiKeyOut],
    dependencies=[Depends(require_admin)],
)
def list_api_keys(tenant_id: str, db: Session = Depends(get_db)) -> list[ApiKey]:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    return (
        db.query(ApiKey)
        .filter(ApiKey.tenant_id == tenant_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def revoke_api_key(
    tenant_id: str, key_id: str, db: Session = Depends(get_db)
) -> None:
    api_key = db.get(ApiKey, key_id)
    if api_key is None or api_key.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="api key not found")
    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(timezone.utc)
        db.commit()
