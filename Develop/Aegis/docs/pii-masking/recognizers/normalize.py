"""日本語テキストの事前正規化ユーティリティ.

PII 検出前に呼び出して全角数字や記号のばらつきを吸収する。
"""

from __future__ import annotations

import unicodedata


def normalize_for_pii(text: str) -> str:
    """Normalize text for PII matching.

    - 全角 → 半角 (数字・英字・括弧)
    - 全角ハイフン類を半角 '-' に統一
    - 連続空白を 1 個に
    """
    # NFKC で全角→半角を一括変換
    text = unicodedata.normalize("NFKC", text)

    # ハイフン類を統一
    hyphen_chars = "‐‑‒–—―−ー"
    for ch in hyphen_chars:
        text = text.replace(ch, "-")

    # 連続空白 → 1
    text = " ".join(text.split())

    return text
