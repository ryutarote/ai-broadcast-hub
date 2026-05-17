"""Discord webhook notifications for posting events.

If DISCORD_WEBHOOK_URL is not set, falls back to stdout so the operator
still sees what happened (cron will mail the output).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

from .config import CONFIG

logger = logging.getLogger(__name__)

# 8MB is Discord's free-tier upload cap.
_MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024


def notify(
    text: str,
    *,
    caption: str = "",
    video_path: Path | None = None,
    success: bool = True,
) -> None:
    webhook = CONFIG.discord_webhook_url.strip()
    prefix = "✅" if success else "❌"
    full = f"{prefix} {text}"

    if not webhook:
        print(full)
        if caption:
            print("--- caption ---")
            print(caption)
        return

    embed = {
        "title": "卒業計画 自動投稿",
        "description": full[:1800],
        "color": 0x00F0FF if success else 0xFF3366,
    }
    if caption:
        embed["fields"] = [
            {"name": "TikTok キャプション", "value": caption[:1000]}
        ]
    payload = {"embeds": [embed]}

    try:
        if (
            video_path
            and video_path.exists()
            and video_path.stat().st_size < _MAX_ATTACHMENT_BYTES
        ):
            with video_path.open("rb") as fh:
                requests.post(
                    webhook,
                    data={"payload_json": json.dumps(payload)},
                    files={"file": (video_path.name, fh, "video/mp4")},
                    timeout=120,
                )
        else:
            requests.post(webhook, json=payload, timeout=30)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Discord notify failed: %s", exc)
        print(full)
