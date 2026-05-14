"""Shared pytest config.

注意：scanner テストは spaCy ja_core_news_md のロードが必要なため、
モデル未インストール環境では @pytest.mark.skip にすることを検討。
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config, items):
    """Mark tests requiring spaCy ja_core_news_md when not installed."""
    try:
        import spacy

        spacy.load("ja_core_news_md")
        ja_available = True
    except Exception:
        ja_available = False

    if ja_available:
        return

    skip_ja = pytest.mark.skip(reason="spaCy ja_core_news_md not installed")
    for item in items:
        # scanner系のテストはspaCyを必要とする
        if "test_scanner" in item.nodeid:
            item.add_marker(skip_ja)
