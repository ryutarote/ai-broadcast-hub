"""Runtime configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get(
        "AEGIS_DATABASE_URL", "sqlite:///./aegis_dev.db"
    )
    api_key_prefix: str = "aeg_live_"
    admin_token: str = os.environ.get("AEGIS_ADMIN_TOKEN", "dev-admin-token")
    default_daily_budget_jpy: int = 50000
    default_monthly_budget_jpy: int = 500000


settings = Settings()
