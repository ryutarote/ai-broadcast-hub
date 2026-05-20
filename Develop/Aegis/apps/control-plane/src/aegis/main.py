"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .routes import (
    analytics,
    api_keys,
    deletion,
    events,
    exports,
    health,
    reports,
    tenants,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Aegis Control Plane",
    version="0.1.0",
    description="MVP backend for Aegis Managed AI Operations.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(tenants.router)
app.include_router(api_keys.router)
app.include_router(events.router)
app.include_router(analytics.router)
app.include_router(exports.router)
app.include_router(reports.admin_router)
app.include_router(reports.tenant_router)
app.include_router(deletion.router)


STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
