"""End-to-end pipeline runner.

For each post entry in posts/posts.json:
  1. TTS each narration line via AivisSpeech (ろてじん)
  2. Concatenate per-line WAV files with small pauses
  3. Generate (or reuse) a background image (black, or AI)
  4. Build ASS subtitles with scene-level telops + per-line subtitles + CTA
  5. ffmpeg compose -> output/final/{id}.mp4
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .compose import compose_video, concat_audio, ensure_ffmpeg, ffprobe_duration
from .config import CONFIG
from .image_gen import generate_scene_image, make_black_background
from .subtitle import build_ass
from .tts import AivisTTS


SCENE_GAP_SEC = 0.35   # pause between scenes
LINE_GAP_SEC = 0.15    # pause between lines inside a scene

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_posts() -> list[dict]:
    if not CONFIG.posts_file.exists():
        raise FileNotFoundError(
            f"posts.json not found at {CONFIG.posts_file}"
        )
    return json.loads(CONFIG.posts_file.read_text(encoding="utf-8"))


def synthesize_post_audio(post: dict, tts: AivisTTS) -> tuple[Path, list[dict]]:
    """TTS every line, concat them, return (audio_path, scenes_with_timing)."""
    post_id = post["id"]
    audio_post_dir = CONFIG.audio_dir / post_id
    audio_post_dir.mkdir(parents=True, exist_ok=True)

    parts: list[Path] = []
    scenes_timing: list[dict] = []
    cursor = 0.0
    line_index = 0

    for s_i, scene in enumerate(post["scenes"]):
        scene_start = cursor
        subtitles: list[dict] = []
        for line in scene["lines"]:
            wav = audio_post_dir / f"{s_i:02d}_{line_index:03d}.wav"
            if not wav.exists():
                tts.synthesize(line, wav)
            duration = ffprobe_duration(wav)
            subtitles.append(
                {
                    "text": line,
                    "start": cursor,
                    "end": cursor + duration,
                }
            )
            parts.append(wav)
            cursor += duration + LINE_GAP_SEC
            line_index += 1
        cursor = cursor - LINE_GAP_SEC + SCENE_GAP_SEC  # swap line gap -> scene gap

        scenes_timing.append(
            {
                "telop": scene.get("telop", ""),
                "start": scene_start,
                "end": cursor - SCENE_GAP_SEC,
                "subtitles": subtitles,
            }
        )

    audio_path = audio_post_dir / "full.wav"
    concat_audio(parts, audio_path, gap_sec=LINE_GAP_SEC)
    return audio_path, scenes_timing


def background_for_post(post: dict) -> Path:
    prompt = (post.get("image_prompt") or "").strip()
    if not prompt:
        return make_black_background(
            CONFIG.video_width,
            CONFIG.video_height,
            CONFIG.image_dir / "_black.png",
        )
    out = CONFIG.image_dir / f"{post['id']}_bg.png"
    return generate_scene_image(prompt, out)


def render_post(post: dict, tts: AivisTTS) -> Path:
    post_id = post["id"]
    final_mp4 = CONFIG.final_dir / f"{post_id}.mp4"
    if final_mp4.exists():
        logger.info("[%s] already rendered, skipping", post_id)
        return final_mp4

    logger.info("[%s] %s", post_id, post.get("title", ""))

    audio_path, scenes_timing = synthesize_post_audio(post, tts)
    audio_duration = ffprobe_duration(audio_path)
    # CTA appears immediately after narration ends - no dead silence gap.
    cta_offset = audio_duration

    bg_path = background_for_post(post)
    ass_path = CONFIG.subtitle_dir / f"{post_id}.ass"
    build_ass(
        scenes_with_timing=scenes_timing,
        title=post.get("title", ""),
        cta_text=post.get("cta", ""),
        cta_offset_sec=cta_offset,
        out_path=ass_path,
        episode=post.get("episode"),
        arc=post.get("arc"),
    )

    boundaries = [s["start"] for s in scenes_timing]
    compose_video(
        audio_path, bg_path, ass_path, final_mp4,
        scene_boundaries=boundaries,
    )
    logger.info("[%s] done -> %s", post_id, final_mp4)
    return final_mp4


def main() -> int:
    parser = argparse.ArgumentParser(description="TikTok video generator")
    parser.add_argument(
        "--id",
        action="append",
        default=[],
        help="Render only specific post id(s). Repeat to add more.",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Do not attempt to install the voice model (assume installed).",
    )
    args = parser.parse_args()

    ensure_ffmpeg()

    tts = AivisTTS()
    tts.wait_until_ready(timeout_sec=120)
    if not args.skip_install:
        tts.install_model()

    posts = load_posts()
    targets = (
        [p for p in posts if p["id"] in set(args.id)] if args.id else posts
    )
    if not targets:
        logger.error("No posts match the given ids.")
        return 2

    for post in targets:
        try:
            render_post(post, tts)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[%s] FAILED: %s", post.get("id", "?"), exc)

    return 0


if __name__ == "__main__":
    sys.exit(main())
