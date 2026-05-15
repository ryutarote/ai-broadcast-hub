"""Pluggable AI image generation for scene backgrounds.

Defaults to a tasteful "near-black" radial gradient with subtle noise so the
final video doesn't read as a flat black void on phone screens. When
IMAGE_GEN_BACKEND is set, an AI image is generated per scene.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import random
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter

from .config import CONFIG

logger = logging.getLogger(__name__)


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def make_designed_background(width: int, height: int, out_path: Path) -> Path:
    """Generate a near-black background with a subtle radial vignette and grain.

    This reads as 'dark' on phones but adds depth so the canvas doesn't feel
    empty between telop and subtitle blocks.
    """
    if out_path.exists():
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Start with a near-black canvas (#080808) instead of pure #000000.
    base = Image.new("RGB", (width, height), (8, 8, 10))

    # Radial vignette: brighter at center (~ rgb 28,28,32), darker at edges.
    overlay = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(overlay)
    cx, cy = width // 2, int(height * 0.42)
    max_r = int((width**2 + height**2) ** 0.5 / 1.6)
    # Draw concentric ellipses with decreasing brightness.
    steps = 40
    for i in range(steps):
        rr = int(max_r * (1 - i / steps))
        v = int(36 * (1 - i / steps))  # max brightness ~36
        draw.ellipse(
            (cx - rr, cy - rr, cx + rr, cy + rr), fill=v
        )
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=160))

    # Add vignette to base.
    base_px = base.load()
    over_px = overlay.load()
    rng = random.Random(42)
    for y in range(height):
        for x in range(width):
            v = over_px[x, y]
            r, g, b = base_px[x, y]
            # Subtle film grain ±4.
            n = rng.randint(-3, 3)
            base_px[x, y] = (
                max(0, min(255, r + v + n)),
                max(0, min(255, g + v + n)),
                max(0, min(255, b + int(v * 1.05) + n)),
            )

    base.save(out_path, "PNG", optimize=True)
    return base.filename if hasattr(base, "filename") else out_path  # type: ignore[return-value]


def make_black_background(width: int, height: int, out_path: Path) -> Path:
    """Backward compat alias - now returns the designed background."""
    return make_designed_background(width, height, out_path)


def generate_scene_image(prompt: str, out_path: Path) -> Path:
    backend = CONFIG.image_gen_backend.lower().strip()
    if not backend:
        return make_designed_background(
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

    return make_designed_background(
        CONFIG.video_width, CONFIG.video_height, out_path
    )


def _generate_openai(prompt: str, out_path: Path) -> Path:
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
    _fit_to_target(out_path)
    return out_path


def _generate_stability(prompt: str, out_path: Path) -> Path:
    if not CONFIG.stability_api_key:
        raise RuntimeError("STABILITY_API_KEY is not set")
    r = requests.post(
        "https://api.stability.ai/v2beta/stable-image/generate/core",
        headers={
            "Authorization": f"Bearer {CONFIG.stability_api_key}",
            "Accept": "image/*",
        },
        files={"none": ""},
        data={"prompt": prompt, "aspect_ratio": "9:16", "output_format": "png"},
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
