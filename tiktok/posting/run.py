"""Daily posting entrypoint.

Picks the next un-posted video from the queue, uploads (or asks the
operator to upload), and updates state.json.

Usage:
    python -m posting.run                # post the next queued video
    python -m posting.run --dry-run      # show what would be posted
    python -m posting.run --id 003       # force a specific post (for retry)
    python -m posting.run --reset        # rebuild the queue from scratch
"""

from __future__ import annotations

import argparse
import logging
import sys

from .captions import parse_captions
from .config import CONFIG
from .notify import notify
from .state import PostingState
from .uploader import post

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def _build_queue(captions: dict[str, str]) -> list[str]:
    ids = sorted(captions.keys())
    if not CONFIG.include_intro:
        ids = [i for i in ids if i != "000"]
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily TikTok poster")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be posted without uploading.",
    )
    parser.add_argument(
        "--id",
        help="Force posting a specific post id (still updates state).",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Rebuild the queue (does NOT clear posted history).",
    )
    args = parser.parse_args()

    captions = parse_captions(CONFIG.captions_file)
    if not captions:
        logger.error("No captions parsed from %s", CONFIG.captions_file)
        return 2

    state = PostingState(CONFIG.state_file)
    if args.reset:
        state.data["queue"] = _build_queue(captions)
        state.save()
        logger.info("Queue reset; %d items", len(state.data["queue"]))

    state.ensure_queue(_build_queue(captions))

    target_id = args.id or state.next_id()
    if not target_id:
        notify(
            "全話投稿済み。シリーズ完結。次のアークを企画してください。",
            success=True,
        )
        return 0

    if target_id not in captions:
        notify(f"キャプションが見つからない: {target_id}", success=False)
        return 1

    video_path = CONFIG.video_dir / f"{target_id}.mp4"
    if not video_path.exists():
        msg = f"動画ファイルが見つからない: {video_path}"
        logger.error(msg)
        state.mark_failed(target_id, msg)
        notify(msg, success=False)
        return 1

    caption = captions[target_id]
    logger.info("Target: %s  Video: %s", target_id, video_path)

    if args.dry_run:
        print(f"--- DRY RUN: {target_id} ---")
        print(f"video: {video_path}")
        print("caption:")
        print(caption)
        return 0

    success, url, note = post(video_path, caption)
    if success:
        state.mark_posted(target_id, url=url, note=note)
        text = (
            f"第{int(target_id)}話 投稿完了 (mode={CONFIG.mode})"
            + (f" → {url}" if url else "")
        )
        # Only attach the video for manual mode (operator needs the file).
        attach = video_path if CONFIG.mode.lower() != "auto" else None
        notify(text, caption=caption, video_path=attach, success=True)
        return 0

    state.mark_failed(target_id, note)
    notify(
        f"第{int(target_id)}話 投稿失敗: {note}\n手動投稿が必要です。",
        caption=caption,
        video_path=video_path,
        success=False,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
