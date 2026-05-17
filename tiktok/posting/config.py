"""Configuration for the daily posting subsystem."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class PostingConfig:
    # TikTok account
    tiktok_username: str = _get("TIKTOK_USERNAME", "ex_gambler_kazuki")

    # Upload mode: "auto" uses tiktok-uploader, "manual" only notifies.
    # Default is "manual" because automated TikTok uploaders are routinely
    # broken by TikTok UI changes and may put the account at risk.
    mode: str = _get("POSTING_MODE", "manual")

    # Cookies path for tiktok-uploader (Netscape cookies.txt format).
    cookies_path: Path = Path(
        _get("TIKTOK_COOKIES_PATH", str(ROOT / "secrets" / "cookies.txt"))
    )

    # Notification webhook (Discord). Optional, but strongly recommended.
    discord_webhook_url: str = _get("DISCORD_WEBHOOK_URL", "")

    # Whether to start the queue with the intro (000) or skip to 001.
    include_intro: bool = _get("INCLUDE_INTRO", "true").lower() == "true"

    # Paths
    root: Path = ROOT
    posts_file: Path = ROOT / "posts" / "posts.json"
    captions_file: Path = ROOT / "captions.md"
    state_file: Path = ROOT / "posting" / "state.json"
    video_dir: Path = ROOT / "output" / "final"


CONFIG = PostingConfig()
