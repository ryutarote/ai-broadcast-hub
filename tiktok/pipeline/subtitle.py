"""ASS subtitle generator (burned into video via ffmpeg)."""

from __future__ import annotations

from pathlib import Path

from .config import CONFIG


def _ass_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - h * 3600 - m * 60
    return f"{h:01d}:{m:02d}:{s:05.2f}"


def _escape(text: str) -> str:
    return text.replace("\n", "\\N").replace("{", "(").replace("}", ")")


def build_ass(
    scenes_with_timing: list[dict],
    cta_text: str,
    cta_offset_sec: float,
    out_path: Path,
) -> Path:
    """Build an ASS file with two styles:

    - Telop: large white text near the top, displayed for the full scene.
    - Subtitle: smaller text at the bottom, one entry per narration sentence.
    """
    w, h = CONFIG.video_width, CONFIG.video_height
    font = "Noto Sans CJK JP"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Telop,{font},96,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,6,2,8,80,80,260,1
Style: Subtitle,{font},56,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,4,2,2,80,80,220,1
Style: CTA,{font},72,&H0000F0FF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,2,5,80,80,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []
    for scene in scenes_with_timing:
        start = scene["start"]
        end = scene["end"]
        telop = _escape(scene.get("telop", "").strip())
        if telop:
            events.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},"
                f"Telop,,0,0,0,,{telop}"
            )
        # Per-sentence subtitles
        for sub in scene.get("subtitles", []):
            events.append(
                f"Dialogue: 0,{_ass_time(sub['start'])},"
                f"{_ass_time(sub['end'])},Subtitle,,0,0,0,,"
                f"{_escape(sub['text'])}"
            )

    if cta_text:
        cta_end = cta_offset_sec + 4.0
        events.append(
            f"Dialogue: 0,{_ass_time(cta_offset_sec)},{_ass_time(cta_end)},"
            f"CTA,,0,0,0,,{_escape(cta_text)}"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out_path
