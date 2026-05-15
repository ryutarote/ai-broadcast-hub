"""Install the ろてじん voice model on the running AivisSpeech Engine.

Usage:
  python -m tools.install_voice

Idempotent: skips if the model is already present.
"""

from __future__ import annotations

import logging
import sys

from pipeline.tts import AivisTTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> int:
    tts = AivisTTS()
    tts.wait_until_ready(timeout_sec=180)
    tts.install_model()
    style_id = tts.resolve_style_id()
    print(f"OK: voice ready (style id={style_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
