"""Pluggable AI image generation for scene backgrounds.

Defaults to a pure-black background (most TikTok scripts in this project use
black + telop). When IMAGE_GEN_BACKEND is set, an AI image is generated per
scene with a prompt derived from the scene metadata.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from pathlib import Path

import requests
from PIL import Image

from .config import CONFIG

logger = logging.getLogger(__name__)


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def make_black_background(width: int, height: int, out_path: Path) -> Path:
    """Generate a pure black PNG to use as a scene background."""
    if out_path.exists():
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), (0, 0, 0))
    img.save(out_path)
    return out_path


def generate_scene_image(prompt: str, out_path: Path) -> Path:
    """Generate an image for a scene using the configured backend.

    Falls back to a black background when no backend is configured or when
    generation fails (the pipeline must keep running).
    """
    backend = CONFIG.image_gen_backend.lower().strip()
    if not backend:
        return make_black_background(
            CONFIG.video_width, CONFIG.video_height, out_path
        )

    if out_path.exists():
        return out_path

    try:
        if backend == "openai":
            return _generate_openai(prompt, out_path)
        if backend == "stability":
            return _generate_stability(prompt, out_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Image generation failed (%s): %s", backend, exc)

    return make_black_background(
        CONFIG.video_width, CONFIG.video_height, out_path
    )


def _generate_openai(prompt: str, out_path: Path) -> Path:
    """OpenAI gpt-image-1 backend."""
    if not CONFIG.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={
            "Authorization": f"Bearer {CONFIG.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-image-1",
            "prompt": prompt,
            "size": "1024x1792",
            "n": 1,
        },
        timeout=180,
    )
    r.raise_for_status()
    payload = r.json()
    b64 = payload["data"][0]["b64_json"]
    raw = base64.b64decode(b64)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(raw)
    # Resize/letterbox to target resolution
    _fit_to_target(out_path)
    return out_path


def _generate_stability(prompt: str, out_path: Path) -> Path:
    """Stability AI (SDXL/Core) backend."""
    if not CONFIG.stability_api_key:
        raise RuntimeError("STABILITY_API_KEY is not set")
    r = requests.post(
        "https://api.stability.ai/v2beta/stable-image/generate/core",
        headers={
            "Authorization": f"Bearer {CONFIG.stability_api_key}",
            "Accept": "image/*",
        },
        files={"none": ""},
        data={
            "prompt": prompt,
            "aspect_ratio": "9:16",
            "output_format": "png",
        },
        timeout=180,
    )
    r.raise_for_status()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)
    _fit_to_target(out_path)
    return out_path


def _fit_to_target(path: Path) -> None:
    target_w, target_h = CONFIG.video_width, CONFIG.video_height
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = max(target_w / w, target_h / h)
    new_size = (int(w * scale), int(h * scale))
    img = img.resize(new_size, Image.LANCZOS)
    left = (img.size[0] - target_w) // 2
    top = (img.size[1] - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))
    img.save(path)


def image_for_scene(scene: dict, scene_index: int, post_id: str) -> Path:
    """Resolve (or generate) the background image for a single scene."""
    prompt = scene.get("image_prompt", "").strip()
    visual = scene.get("visual", "black").strip().lower()

    if visual == "black" or not prompt:
        out = CONFIG.image_dir / f"{post_id}_black.png"
        return make_black_background(
            CONFIG.video_width, CONFIG.video_height, out
        )

    out = CONFIG.image_dir / f"{post_id}_{scene_index:02d}_{_hash(prompt)}.png"
    return generate_scene_image(prompt, out)
