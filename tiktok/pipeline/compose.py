"""Video composition (ffmpeg).

Produces a polished, motion-rich 1080x1920 mp4:
- Subtle Ken-Burns zoom on the background to avoid the "static slide" feel
- Burned-in ASS subtitles (title, telops, per-line subs, CTA)
- Bottom progress bar so viewers feel time passing (retention lever)
- Top + bottom safe-area gradient bars that improve contrast for telops/CTA
- A soft ambient pad mixed under the narration at -28 dB
"""

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
    out_path.parent.mkdir(parents=True, exist_ok=True)
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
                "anullsrc=channel_layout=mono:sample_rate=44100",
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
    progress_bar: bool = True,
    tail_seconds: float = 3.2,
    scene_boundaries: list[float] | None = None,
) -> Path:
    """Compose final mp4.

    Pads the audio track with ``tail_seconds`` of silence so the CTA card has
    time to display after the last narration line ends.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    audio_dur = ffprobe_duration(audio_path)
    total_dur = audio_dur + tail_seconds

    # 1. Pad voice with tail silence so the CTA card has time to play.
    padded_voice = audio_path.with_name(audio_path.stem + ".padded.wav")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(audio_path),
            "-af",
            f"apad=pad_dur={tail_seconds},aresample=44100",
            "-ac",
            "1",
            "-t",
            f"{total_dur:.3f}",
            str(padded_voice),
        ],
        check=True,
        capture_output=True,
    )

    # 2. Mix in an audible ambient bed: 5-voice A-minor pad
    #    (A1 sub / A2 / C3 / E3 / A3) with slow tremolo + warm lowpass.
    #    Sits roughly -10 to -14 LUFS under the voice — loud enough that
    #    the 27s of inter-line silence is no longer dead air.
    #    Uses amix normalize=0 so input weights are honored verbatim
    #    (default amix divides by N which made the bed inaudible).
    mixed_audio = audio_path.with_name(audio_path.stem + ".mix.wav")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(padded_voice),
            "-f", "lavfi", "-t", f"{total_dur:.3f}",
            "-i", "sine=frequency=55:sample_rate=44100",     # A1 sub
            "-f", "lavfi", "-t", f"{total_dur:.3f}",
            "-i", "sine=frequency=110:sample_rate=44100",    # A2
            "-f", "lavfi", "-t", f"{total_dur:.3f}",
            "-i", "sine=frequency=130.81:sample_rate=44100", # C3 (minor 3rd)
            "-f", "lavfi", "-t", f"{total_dur:.3f}",
            "-i", "sine=frequency=164.81:sample_rate=44100", # E3 (5th)
            "-f", "lavfi", "-t", f"{total_dur:.3f}",
            "-i", "sine=frequency=220:sample_rate=44100",    # A3
            "-filter_complex",
            (
                # Per-voice trim (peaks summed will not exceed 1.0).
                "[1:a]volume=0.14[a0];"
                "[2:a]volume=0.22[a1];"
                "[3:a]volume=0.14[a2];"
                "[4:a]volume=0.12[a3];"
                "[5:a]volume=0.10[a4];"
                "[a0][a1][a2][a3][a4]"
                "amix=inputs=5:duration=longest:"
                "normalize=0:dropout_transition=0,"
                "tremolo=f=0.20:d=0.4,"
                # Warm low-pass: takes harsh edge off pure sines.
                "lowpass=f=1400,"
                # Final bed gain (large because amix didn't scale).
                "volume=1.6,"
                "aformat=sample_fmts=s16:channel_layouts=mono[bed];"
                # Mix bed in well below voice (0.55) but always audible.
                "[0:a][bed]amix=inputs=2:duration=first:"
                "weights='1 0.55':normalize=0:dropout_transition=0,"
                # Slightly gentler than before: LRA 9->12 lets the voice
                # breathe instead of being clamped flat; TP -1.5->-2.0
                # gives extra peak headroom so it doesn't sound squashed.
                "loudnorm=I=-14:LRA=12:TP=-2.0,"
                "aresample=44100"
            ),
            "-ac", "1",
            "-t", f"{total_dur:.3f}",
            str(mixed_audio),
        ],
        check=True,
        capture_output=True,
    )
    audio_path = mixed_audio

    w = CONFIG.video_width
    h = CONFIG.video_height

    ass_path_escaped = (
        str(subtitle_path).replace("\\", "\\\\").replace(":", r"\:")
    )

    # Pipeline:
    #   1. Scale bg to slightly larger than target.
    #   2. Slow zoompan (Ken-Burns) for subtle life.
    #   3. Crop to target.
    #   4. Overlay top + bottom gradient strips for telop/CTA contrast.
    #   5. Burn ASS.
    #   6. Optional: draw progress bar at bottom edge.
    fps = CONFIG.video_fps
    n_frames = int(total_dur * fps)

    # Slow zoom from 1.00 -> 1.08 over the full duration.
    zoom_expr = f"min(zoom+0.0006,1.08)"

    progress_y = h - 6
    progress_h = 6
    progress_bar_filter = (
        f",drawbox=x=0:y={progress_y}:w='iw*(t/{total_dur:.3f})':"
        f"h={progress_h}:color=0xE14F1F@0.9:t=fill"
    ) if progress_bar else ""

    # Yellow accent divider between telop and subtitle.
    # Sits between the centered telop (ends ~y=850) and subtitle (starts
    # ~y=1000). Hidden during the CTA tail so the yellow CTA card reads
    # as the focal element.
    divider_y = 920
    divider_w = int(w * 0.35)
    divider_x = (w - divider_w) // 2
    divider_filter = (
        f",drawbox=x={divider_x}:y={divider_y}:w={divider_w}:h=4:"
        f"color=0xE14F1F@0.85:t=fill:"
        f"enable='lt(t,{audio_dur - 0.3:.3f})'"
    )

    # Scene-change flash: subtle white pulse at each scene boundary
    # to give the eye a beat to follow.
    flash_filters: list[str] = []
    if scene_boundaries:
        for b in scene_boundaries[1:]:  # skip t=0
            # 80 ms white overlay at 0.18 opacity = subtle pop.
            flash_filters.append(
                f"drawbox=x=0:y=0:w={w}:h={h}:color=white@0.18:t=fill:"
                f"enable='between(t,{max(0, b - 0.04):.3f},{b + 0.04:.3f})'"
            )
    flash_filter = ("," + ",".join(flash_filters)) if flash_filters else ""

    # The original design used solid 0.45-opacity bands at top/bottom and
    # cyan side bars to create a "framed" feel. Pro reviewer flagged that
    # the bands + bars shrink the perceived screen on phones. We now drop
    # the side bars entirely and use very light bands (0.20) only as a
    # contrast helper for the telop/CTA against the zooming background.
    top_band_filter = (
        f",drawbox=x=0:y=0:w={w}:h=160:color=black@0.20:t=fill"
    )
    bottom_band_filter = (
        f",drawbox=x=0:y={h - 180}:w={w}:h=180:color=black@0.20:t=fill"
    )
    side_bars_filter = ""
    brand_filter = ""

    # Full-width amber CTA band drawn behind the CTA text. Active only
    # during the CTA window (audio_dur .. audio_dur + 4s). 3 lines of
    # 92pt text = ~380px tall; band is sized to comfortably contain it.
    cta_band_h = 420
    cta_band_y = h // 2 - cta_band_h // 2 - 40
    cta_band_filter = (
        f",drawbox=x=0:y={cta_band_y}:w={w}:h={cta_band_h}:"
        f"color=0xE14F1F@1.0:t=fill:"
        f"enable='gte(t,{audio_dur:.3f})'"
    )

    vf = (
        f"scale={int(w*1.15)}:{int(h*1.15)}:flags=lanczos,"
        f"zoompan=z='{zoom_expr}':d={n_frames}:s={w}x{h}:fps={fps}"
        f"{top_band_filter}"
        f"{bottom_band_filter}"
        f"{side_bars_filter}"
        f"{cta_band_filter}"
        f",ass='{ass_path_escaped}'"
        f"{divider_filter}"
        f"{brand_filter}"
        f"{flash_filter}"
        f"{progress_bar_filter}"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-framerate",
        str(fps),
        "-t",
        f"{total_dur:.3f}",
        "-i",
        str(background_path),
        "-i",
        str(audio_path),
        "-filter_complex",
        f"[0:v]{vf}[v]",
        "-map",
        "[v]",
        "-map",
        "1:a",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "44100",
        "-t",
        f"{total_dur:.3f}",
        "-r",
        str(fps),
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    logger.info("ffmpeg compose -> %s", out_path.name)
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        logger.error("ffmpeg stderr: %s", proc.stderr.decode("utf-8", "ignore")[-2000:])
        raise RuntimeError(f"ffmpeg failed for {out_path}")
    return out_path


def ensure_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(
                f"{tool} is required. Install via: apt-get install -y ffmpeg"
            )
