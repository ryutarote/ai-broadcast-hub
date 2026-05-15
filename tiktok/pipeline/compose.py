"""Video composition (ffmpeg)."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from .config import CONFIG

logger = logging.getLogger(__name__)


def ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    out = subprocess.check_output(cmd, text=True)
    return float(json.loads(out)["format"]["duration"])


def concat_audio(parts: list[Path], out_path: Path, gap_sec: float = 0.25) -> Path:
    """Concatenate wav files with a short silent gap between scenes."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Build a concat-demuxer file (with silence between parts).
    list_path = out_path.with_suffix(".txt")
    silence_path = out_path.parent / f"_silence_{int(gap_sec * 1000)}ms.wav"
    if not silence_path.exists():
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=channel_layout=mono:sample_rate=44100",
                "-t",
                str(gap_sec),
                str(silence_path),
            ],
            check=True,
            capture_output=True,
        )

    with list_path.open("w", encoding="utf-8") as f:
        for i, p in enumerate(parts):
            f.write(f"file '{p.resolve()}'\n")
            if i < len(parts) - 1:
                f.write(f"file '{silence_path.resolve()}'\n")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c:a",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "1",
            str(out_path),
        ],
        check=True,
        capture_output=True,
    )
    list_path.unlink(missing_ok=True)
    return out_path


def compose_video(
    audio_path: Path,
    background_path: Path,
    subtitle_path: Path,
    out_path: Path,
) -> Path:
    """Compose final mp4 with: background image + audio + burned subtitles."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = ffprobe_duration(audio_path)

    # Burned subtitles via ass filter. Escape path for ffmpeg filter.
    ass_path_escaped = str(subtitle_path).replace(":", r"\:").replace(",", r"\,")

    vf = (
        f"scale={CONFIG.video_width}:{CONFIG.video_height}:"
        f"force_original_aspect_ratio=increase,"
        f"crop={CONFIG.video_width}:{CONFIG.video_height},"
        f"ass={ass_path_escaped}"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-framerate",
        str(CONFIG.video_fps),
        "-i",
        str(background_path),
        "-i",
        str(audio_path),
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-t",
        f"{duration + 4.5:.2f}",  # extra time for CTA card
        "-vf",
        vf,
        "-r",
        str(CONFIG.video_fps),
        str(out_path),
    ]

    logger.info("ffmpeg compose -> %s", out_path.name)
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def ensure_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(
                f"{tool} is required. Install via: apt-get install -y ffmpeg"
            )
