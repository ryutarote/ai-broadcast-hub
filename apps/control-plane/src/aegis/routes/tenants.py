"""Tenant CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..db import get_db
from ..models import Tenant
from ..schemas import TenantCreate, TenantOut, TenantUpdate

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


@router.post(
    "",
    response_model=TenantOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)) -> Tenant:
    tenant = Tenant(
        name=payload.name,
        plan=payload.plan,
        contact_email=payload.contact_email,
        daily_budget_jpy=payload.daily_budget_jpy,
        monthly_budget_jpy=payload.monthly_budget_jpy,
        slack_webhook=payload.slack_webhook,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.get("", response_model=list[TenantOut], dependencies=[Depends(require_admin)])
def list_tenants(db: Session = Depends(get_db)) -> list[Tenant]:
    return db.query(Tenant).order_by(Tenant.created_at.desc()).all()


@router.get(
    "/{tenant_id}",
    response_model=TenantOut,
    dependencies=[Depends(require_admin)],
)
def get_tenant(tenant_id: str, db: Session = Depends(get_db)) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    return tenant


@router.patch(
    "/{tenant_id}",
    response_model=TenantOut,
    dependencies=[Depends(require_admin)],
)
def update_tenant(
    tenant_id: str, payload: TenantUpdate, db: Session = Depends(get_db)
) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.delete(
    "/{tenant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_tenant(tenant_id: str, db: Session = Depends(get_db)) -> None:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    db.delete(tenant)
    db.commit()
