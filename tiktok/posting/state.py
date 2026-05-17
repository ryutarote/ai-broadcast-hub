"""State management for the daily posting queue.

state.json layout:
    {
      "queue":  ["000", "001", ..., "030"],   # ordered set
      "posted": ["000", "001"],                 # subset already published
      "history": [                              # all attempts (success/fail)
        {"id": "000", "at": "2026-…Z",
         "status": "posted", "url": "…", "note": ""},
         ...
      ]
    }
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PostingState:
    def __init__(self, path: Path) -> None:
        self.path = path
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
        else:
            self.data = {"queue": [], "posted": [], "history": []}

    def ensure_queue(self, ids: list[str]) -> None:
        """Initialize the queue if empty; otherwise leave it alone.

        Useful so we can call this on every run without overwriting the
        progress recorded in a previous run.
        """
        if not self.data.get("queue"):
            self.data["queue"] = list(ids)
            self.save()

    def next_id(self) -> str | None:
        posted = set(self.data.get("posted", []))
        for pid in self.data["queue"]:
            if pid not in posted:
                return pid
        return None

    def mark_posted(self, post_id: str, url: str = "", note: str = "") -> None:
        if post_id not in self.data["posted"]:
            self.data["posted"].append(post_id)
        self.data["history"].append(
            {
                "id": post_id,
                "at": _utcnow_iso(),
                "status": "posted",
                "url": url,
                "note": note,
            }
        )
        self.save()

    def mark_failed(self, post_id: str, error: str) -> None:
        self.data["history"].append(
            {
                "id": post_id,
                "at": _utcnow_iso(),
                "status": "failed",
                "error": error,
            }
        )
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
