"""TikTok upload backends.

Two modes are supported and selected via POSTING_MODE env / config:

  - "auto"    : drive the TikTok web uploader via the PyPI
                ``tiktok-uploader`` package (Selenium + cookies).
                Requires a valid Netscape cookies.txt for the target
                account, headed Chromium not required (runs headless).
  - "manual"  : do not upload; the caller (notify) will surface the
                video file and caption so the operator can post by hand.
                Safer and the default — automated uploaders frequently
                break with TikTok UI changes.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import CONFIG

logger = logging.getLogger(__name__)


class UploadError(RuntimeError):
    pass


def auto_upload(video_path: Path, description: str) -> str:
    """Run the tiktok-uploader against the configured account.

    Returns the resulting tiktok URL if the uploader exposes it, otherwise
    an empty string. Raises UploadError on failure.
    """
    try:
        from tiktok_uploader.upload import upload_video
    except ImportError as exc:
        raise UploadError(
            "tiktok-uploader package is not installed. "
            "Run `pip install tiktok-uploader`."
        ) from exc

    cookies = CONFIG.cookies_path
    if not cookies.exists():
        raise UploadError(
            f"cookies file not found at {cookies}. "
            f"Export your TikTok session cookies (Netscape format) and "
            f"set TIKTOK_COOKIES_PATH or place at the default location."
        )

    logger.info(
        "uploading %s as @%s ...",
        video_path.name,
        CONFIG.tiktok_username,
    )
    try:
        result = upload_video(
            filename=str(video_path),
            description=description,
            cookies=str(cookies),
            headless=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise UploadError(f"tiktok-uploader raised: {exc}") from exc

    # The library returns either None or a list of failed videos. An empty
    # list (or None) means success.
    if isinstance(result, list) and result:
        raise UploadError(f"tiktok-uploader reported failures: {result}")

    return ""  # URL is not reliably surfaced by the lib


def post(video_path: Path, description: str) -> tuple[bool, str, str]:
    """Returns (success, tiktok_url, note)."""
    if CONFIG.mode.lower() == "auto":
        try:
            url = auto_upload(video_path, description)
            return True, url, "auto"
        except UploadError as exc:
            return False, "", f"auto upload failed: {exc}"
    # manual mode: caller handles notification with the video + caption
    return True, "", "manual: operator will post"
