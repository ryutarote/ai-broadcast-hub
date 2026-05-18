"""Shared test config: set env vars BEFORE importing aegis modules."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


# Single shared DB per pytest session keeps the two test modules independent
# of each other; the actual ROW data is created anew per test via TestClient
# lifespan that calls `Base.metadata.create_all` (a no-op if tables exist).
_TMP = tempfile.NamedTemporaryFile(
    prefix="aegis_test_", suffix=".db", delete=False
)
_TMP.close()
os.environ.setdefault("AEGIS_DATABASE_URL", f"sqlite:///{_TMP.name}")
os.environ.setdefault("AEGIS_ADMIN_TOKEN", "test-admin-token")

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
