"""Authentication helpers."""

from __future__ import annotations

import hashlib
import secrets

from fastapi import Header, HTTPException, status

from .config import settings


def generate_api_key() -> tuple[str, str, str]:
    """Generate an API key.

    Returns (prefix, plaintext, sha256_hash).
    """
    body = secrets.token_urlsafe(32)
    plaintext = f"{settings.api_key_prefix}{body}"
    prefix = plaintext[: len(settings.api_key_prefix) + 6]
    return prefix, plaintext, hash_key(plaintext)


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Simple admin-token guard for internal endpoints."""
    if not x_admin_token or not secrets.compare_digest(
        x_admin_token, settings.admin_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid admin token",
        )
