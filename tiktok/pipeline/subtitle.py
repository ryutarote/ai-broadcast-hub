"""ASS subtitle generator (burned into video via ffmpeg).

Designed for vertical TikTok (1080x1920) consumption:
- Title card (Hook) burned for the first 2.0s
- Telop: large bold text positioned in the upper-mid safe area (per scene)
- Subtitle: 2-line wrapped text in the middle safe area (per narration line)
- CTA card: large yellow card flashing at the end
- Progress bar overlay handled in compose.py (drawbox)

TikTok safe area:
- Top reserved (username/sound): ~ 220px
- Bottom reserved (caption/buttons): ~ 450px
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import CONFIG


SAFE_TOP = 240
SAFE_BOTTOM = 470  # bigger to keep clear of caption + buttons
# Vertically centered content block:
#   Telop  top  ≈ y=600  (content 600..850)
#   Divider     ≈ y=920
#   Subtitle    ≈ y=1000 (content 1000..1250)
# Screen center y=960 sits between divider and subtitle, balancing the block.
TELOP_Y_FROM_TOP = 600
SUBTITLE_Y_FROM_TOP = 1000


def _ass_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - h * 3600 - m * 60
    return f"{h:01d}:{m:02d}:{s:05.2f}"


def _escape(text: str) -> str:
    return text.replace("{", "(").replace("}", ")")


_NUMBER_RE = re.compile(r"(\d[\d,\.]*[\d万円件％%パーセント円日年時分秒]*)")


def _highlight_numbers(text: str) -> str:
    """Wrap numeric tokens with ASS color override for emphasis (amber).

    Amber #D4A017 (BGR=&H17A0D4) replaces the earlier neon yellow so the
    palette reads as "落ち着いた・男性的" instead of TikTok-flashy.
    """
    def repl(m: re.Match[str]) -> str:
        return r"{\c&H17A0D4&\b1}" + m.group(0) + r"{\c&HFFFFFF&\b0}"
    return _NUMBER_RE.sub(repl, text)


def _wrap_lines(text: str, max_chars: int = 15) -> str:
    """Wrap text into ≤3 visual lines.

    Rules:
    - Prefer Japanese sentence punctuation as break points
    - Never break inside a contiguous number ("99.4%", "1,247日")
    - Fallback: hard char-count break at a safe position
    """
    text = text.strip()
    if len(text) <= max_chars:
        return text

    break_chars = "、。！？"

    # Mark positions inside number runs as unsafe to break at.
    def compute_unsafe(seg: str) -> set[int]:
        u = set()
        in_num = False
        for i, ch in enumerate(seg):
            is_num = ch.isdigit() or ch in ".,%"
            if is_num and in_num:
                u.add(i)
            in_num = is_num
        return u

    def find_break(segment: str) -> int:
        unsafe = compute_unsafe(segment)
        # 1) Punctuation break within max_chars (search backwards).
        for i in range(min(max_chars, len(segment)) - 1, 0, -1):
            if segment[i] in break_chars and i + 1 not in unsafe:
                return i + 1
        # 2) Punctuation right at max_chars.
        if (
            len(segment) > max_chars
            and segment[max_chars] in break_chars
        ):
            return max_chars + 1
        # 3) Hard break - step backwards until safe AND tail >= 3 chars
        #    so we don't strand a single character on the next line.
        pos = min(max_chars, len(segment))
        min_tail = 3
        while pos > 1 and (pos in unsafe or len(segment) - pos < min_tail):
            pos -= 1
        return pos

    lines: list[str] = []
    remaining = text
    # Up to 4 lines so a very long single sentence doesn't overflow the
    # last line off-screen. Three lines of 15 chars = 45 chars, four = 60.
    for _ in range(3):
        if len(remaining) <= max_chars:
            break
        pos = find_break(remaining)
        if pos < len(remaining) and remaining[pos] in break_chars:
            pos += 1
        lines.append(remaining[:pos])
        remaining = remaining[pos:]
    lines.append(remaining)
    return r"\N".join(lines)


def _telop_lines(text: str, max_chars: int = 11) -> str:
    """Wrap a telop into ≤2 lines.

    Rules:
    - Prefer punctuation/separator breaks ("/", "、", "：", "＝", "・", space)
    - Never break inside a contiguous number (e.g. "99.4%", "1,247日")
    - Sized for 96pt Noto CJK Bold on a 1080px canvas with 80px side margins
    """
    text = text.strip()
    if len(text) <= max_chars:
        return text

    # Mark indexes that are *inside* a number-run as "unsafe" to break.
    unsafe = set()
    in_num = False
    for i, ch in enumerate(text):
        is_num = ch.isdigit() or ch in ".,%"
        if is_num and in_num:
            unsafe.add(i)
        in_num = is_num

    break_chars = "/、:=・ 　：＝"
    target = len(text) // 2

    def is_safe(pos: int) -> bool:
        return pos not in unsafe

    # 1) Best candidate: punctuation, safe, close to middle.
    punct = [
        i + 1
        for i, ch in enumerate(text[:-1])
        if ch in break_chars and is_safe(i + 1)
    ]
    if punct:
        best = min(punct, key=lambda i: abs(i - target))
    else:
        # 2) Walk outward from target to find any safe break point.
        best = None
        for delta in range(0, len(text)):
            for candidate in (target - delta, target + delta):
                if 0 < candidate < len(text) and is_safe(candidate):
                    best = candidate
                    break
            if best is not None:
                break
        if best is None:
            best = target

    line1 = text[:best].rstrip()
    line2 = text[best:].lstrip()
    return line1 + r"\N" + line2


def build_ass(
    scenes_with_timing: list[dict],
    title: str,
    cta_text: str,
    cta_offset_sec: float,
    out_path: Path,
    episode: int | None = None,
    arc: str | None = None,
) -> Path:
    """Build a polished ASS subtitle track.

    Layout (1080x1920):
        +--------------------------------+
        |  (240px safe top)              |
        |                                |
        |   [ TITLE CARD 0-2s ]          |
        |                                |
        |   [ TELOP - per scene ]        |
        |                                |
        |   [ SUBTITLE - per line ]      |
        |                                |
        |  (470px safe bottom)           |
        +--------------------------------+
    """
    w, h = CONFIG.video_width, CONFIG.video_height
    font = "Noto Sans CJK JP"

    # Layout (Alignment=8 = top-anchored with MarginV from top):
    #   y=300:  Telop (large, bold, white, dark backdrop, yellow numbers)
    #   y=560:  Yellow divider (rendered in compose.py as drawbox)
    #   y=700:  Subtitle (mid-size, white, narration text)
    telop_margin_v = TELOP_Y_FROM_TOP
    sub_margin_v = SUBTITLE_Y_FROM_TOP
    cta_margin_v = h // 2 - 100

    # Alignment numpad: 8=top-center, 5=middle-center, 2=bottom-center
    # Color codes are &HAABBGGRR (alpha is inverted, 00=opaque, FF=transparent)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
ScaledBorderAndShadow: yes
WrapStyle: 0
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Telop,{font},96,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,1,0,0,0,100,100,2,0,1,7,5,8,80,80,{telop_margin_v},1
Style: Subtitle,{font},64,&H00FFFFFF,&H000000FF,&H00000000,&HB0000000,1,0,0,0,100,100,0,0,1,5,3,8,80,80,{sub_margin_v},1
Style: CTA,{font},92,&H00000000,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,2,0,1,0,0,5,0,0,{cta_margin_v},1
Style: DayCounter,{font},42,&H0017A0D4,&H000000FF,&H00000000,&H40000000,1,0,0,0,100,100,0,0,1,3,2,7,40,40,210,1
Style: CTAArrow,{font},88,&H00000000,&H000000FF,&H00FFFFFF,&H00000000,1,0,0,0,100,100,0,0,1,4,2,2,0,0,440,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []

    # Title is intentionally not rendered as a separate card: the first telop
    # already serves as the hook. Keeping the parameter for API stability.
    _ = title

    total_scenes = len(scenes_with_timing)

    # Extend each scene's visible end to the next scene's start so the gap
    # between narration lines doesn't show a blank canvas.
    extended_ends: list[float] = []
    for i, scene in enumerate(scenes_with_timing):
        if i + 1 < len(scenes_with_timing):
            extended_ends.append(scenes_with_timing[i + 1]["start"])
        else:
            # Last scene: hold telop until the CTA appears.
            extended_ends.append(cta_offset_sec - 0.1)

    # 1. Telops (per scene) - dramatic entry: slight slide from left + scale-pop
    #    + fade. Hold for the full scene length. The entry animation is
    #    intentionally aggressive (450ms) to mark scene transitions clearly.
    #    Scenes flagged "hero": true get 150% font scaling for max impact —
    #    used for climactic numeric statements like "1247日目".
    for i, scene in enumerate(scenes_with_timing, start=1):
        start = scene["start"]
        end = extended_ends[i - 1]
        telop = scene.get("telop", "").strip()
        is_hero = bool(scene.get("hero"))
        safe = _escape(telop)
        wrapped = _telop_lines(safe, max_chars=11) if telop else ""
        highlighted = _highlight_numbers(wrapped) if wrapped else ""
        # Combined effect: quick fade-in + scale pop + settle.
        # Hero variant settles at 200% (2x) so a single-number telop like
        # "1247日目" reads as the visual centerpiece of the slide.
        settle_scale = 200 if is_hero else 100
        pop_scale = settle_scale + 18
        effect = (
            "{"
            "\\fad(100,140)"
            f"\\t(0,80,\\fscx{pop_scale}\\fscy{pop_scale}\\frz-2)"
            f"\\t(80,280,\\fscx{settle_scale}\\fscy{settle_scale}\\frz0)"
            "}"
        )
        if telop:
            events.append(
                f"Dialogue: 2,{_ass_time(start)},{_ass_time(end)},Telop,,0,0,0,,"
                f"{effect}{highlighted}"
            )

    # 2. Subtitles per narration line - quick slide-up entry, with each
    #    subtitle held until the next one starts (or scene ends).
    for s_i, scene in enumerate(scenes_with_timing):
        subs = scene.get("subtitles", [])
        for j, sub in enumerate(subs):
            # End at the next subtitle start (or the scene's extended end).
            if j + 1 < len(subs):
                end_time = subs[j + 1]["start"]
            else:
                end_time = extended_ends[s_i]
            safe = _escape(sub["text"].strip().rstrip("。"))
            wrapped = _wrap_lines(safe)
            highlighted = _highlight_numbers(wrapped)
            sub_effect = (
                "{\\fad(140,180)"
                "\\t(0,180,\\fscx102\\fscy102)"
                "\\t(180,260,\\fscx100\\fscy100)"
                "}"
            )
            events.append(
                f"Dialogue: 3,{_ass_time(sub['start'])},{_ass_time(end_time)},"
                f"Subtitle,,0,0,0,,{sub_effect}{highlighted}"
            )

    # 3. CTA card (last 4s) + animated "↑" arrow pointing to TikTok profile.
    # When the CTA contains "／" markers we honor them as explicit line
    # breaks (each segment becomes its own centered line). Otherwise we fall
    # back to char-count wrapping.
    if cta_text:
        cta_end = cta_offset_sec + 4.0
        safe_cta = _escape(cta_text)
        if "／" in safe_cta:
            segments = [s.strip() for s in safe_cta.split("／") if s.strip()]
            wrapped_cta = r"\N".join(segments)
        else:
            # CTA font is 92pt: ~10 chars max per line.
            wrapped_cta = _wrap_lines(safe_cta, max_chars=10)
        events.append(
            f"Dialogue: 5,{_ass_time(cta_offset_sec)},{_ass_time(cta_end)},"
            f"CTA,,0,0,0,,{{\\fad(250,250)\\t(0,250,\\fscx108\\fscy108)"
            f"\\t(250,520,\\fscx100\\fscy100)}}{wrapped_cta}"
        )
        # Pulsing arrow drawing attention to the profile (top of screen).
        events.append(
            f"Dialogue: 5,{_ass_time(cta_offset_sec + 0.4)},{_ass_time(cta_end)},"
            f"CTAArrow,,0,0,0,,{{\\fad(180,180)"
            f"\\t(0,500,\\fscx115\\fscy115)\\t(500,1000,\\fscx100\\fscy100)"
            f"\\t(1000,1500,\\fscx115\\fscy115)\\t(1500,2000,\\fscx100\\fscy100)"
            f"}}↑ プロフィールへ"
        )

    # 4. Day-counter tag (permanent, top-left). Replaces the old
    #    "卒業計画" brand wordmark — per reviewer, the authority signal
    #    of "1247日目" is the strongest possible always-on element for
    #    a Pachi-Sotsu account. Whatever the channel's current 卒業
    #    day-count is, put it here.
    last_t = scenes_with_timing[-1]["end"] if scenes_with_timing else 0
    end_t = last_t + 5
    counter_text = "卒業 1247日目"  # update via posts.json "day_counter" if needed
    events.append(
        f"Dialogue: 0,{_ass_time(0)},{_ass_time(end_t)},DayCounter,,0,0,0,,"
        f"{{\\fad(400,200)}}{counter_text}"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out_path
