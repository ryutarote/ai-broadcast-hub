"""Parse captions.md into {post_id: caption_text}.

Section headers look like:
    ## 第0話（プロフ固定動画）
    ### 第1話 — タイトル
    ### 第30話 — タイトル ⟨シリーズ完結⟩

The first ``` block under each header is the caption used as the TikTok
description.
"""

from __future__ import annotations

import re
from pathlib import Path


_EP_HEADING_RE = re.compile(r"^#{2,3}\s+第(\d+)話")


def parse_captions(md_path: Path) -> dict[str, str]:
    """Returns {post_id: caption_text}; post_id is zero-padded like "000"."""
    if not md_path.exists():
        raise FileNotFoundError(f"captions.md not found at {md_path}")

    text = md_path.read_text(encoding="utf-8")
    result: dict[str, str] = {}

    current_id: str | None = None
    in_code = False
    buffer: list[str] = []

    for raw in text.split("\n"):
        m = _EP_HEADING_RE.match(raw)
        if m:
            current_id = f"{int(m.group(1)):03d}"
            in_code = False
            buffer = []
            continue
        if current_id and raw.strip() == "```":
            if in_code:
                # End of caption block - record and stop until next heading.
                if current_id not in result:
                    result[current_id] = "\n".join(buffer).strip()
                in_code = False
                current_id = None
                buffer = []
            else:
                in_code = True
            continue
        if in_code:
            buffer.append(raw)

    return result
