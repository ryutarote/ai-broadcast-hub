"""Pipeline configuration (read from environment)."""

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
class Config:
    engine_url: str = _get("AIVIS_ENGINE_URL", "http://localhost:10101")
    voice_model_uuid: str = _get(
        "VOICE_MODEL_UUID", "80fe2db4-5891-4550-a3f3-dff9a91c0946"
    )
    voice_style_name: str = _get("VOICE_STYLE_NAME", "ノーマル")
    video_width: int = int(_get("VIDEO_WIDTH", "1080"))
    video_height: int = int(_get("VIDEO_HEIGHT", "1920"))
    video_fps: int = int(_get("VIDEO_FPS", "30"))
    font_path: str = _get(
        "FONT_PATH", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    )
    image_gen_backend: str = _get("IMAGE_GEN_BACKEND", "")
    openai_api_key: str = _get("OPENAI_API_KEY", "")
    stability_api_key: str = _get("STABILITY_API_KEY", "")

    root: Path = ROOT
    posts_file: Path = ROOT / "posts" / "posts.json"
    audio_dir: Path = ROOT / "output" / "audio"
    image_dir: Path = ROOT / "output" / "images"
    subtitle_dir: Path = ROOT / "output" / "subtitles"
    final_dir: Path = ROOT / "output" / "final"


CONFIG = Config()
