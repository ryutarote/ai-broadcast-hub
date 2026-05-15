"""AivisSpeech Engine TTS client (with Open JTalk fallback).

Talks to a locally running AivisSpeech Engine (VOICEVOX-compatible HTTP API)
to synthesize Japanese speech with the ろてじん Style-Bert-VITS2 model.

When the engine is unreachable (offline/CI), automatically falls back to a
local Open JTalk install so the rest of the pipeline can still run.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

import requests

from .config import CONFIG

logger = logging.getLogger(__name__)

OPEN_JTALK_DICT = "/var/lib/mecab/dic/open-jtalk/naist-jdic"
OPEN_JTALK_VOICE = (
    "/usr/share/hts-voice/nitech-jp-atr503-m001/"
    "nitech_jp_atr503_m001.htsvoice"
)


class AivisTTSError(RuntimeError):
    pass


class AivisTTS:
    def __init__(self, engine_url: str | None = None) -> None:
        self.engine_url = (engine_url or CONFIG.engine_url).rstrip("/")
        self._style_id: int | None = None
        # When True, all synthesize() calls go through Open JTalk.
        self._fallback = os.environ.get("TTS_BACKEND", "").lower() == "open_jtalk"

    def wait_until_ready(self, timeout_sec: int = 120) -> None:
        if self._fallback:
            logger.info("TTS_BACKEND=open_jtalk; skipping AivisSpeech wait.")
            return
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                r = requests.get(f"{self.engine_url}/version", timeout=5)
                if r.ok:
                    logger.info("AivisSpeech Engine ready: %s", r.text.strip())
                    return
            except requests.RequestException:
                pass
            time.sleep(2)
        # Engine not reachable: enable fallback automatically.
        logger.warning(
            "AivisSpeech Engine unreachable at %s; "
            "falling back to Open JTalk (set TTS_BACKEND=aivis to force).",
            self.engine_url,
        )
        self._fallback = True

    def install_model(self, uuid: str | None = None) -> None:
        """Install the AIVM model on the engine. Idempotent."""
        if self._fallback:
            return
        uuid = uuid or CONFIG.voice_model_uuid
        if self._is_installed(uuid):
            logger.info("Voice model already installed: %s", uuid)
            return

        # The engine accepts UUID via the install endpoint and resolves the
        # download URL against Aivis Hub automatically.
        url = f"{self.engine_url}/aivm_models/install"
        logger.info("Installing voice model %s ...", uuid)
        r = requests.post(url, params={"model_uuid": uuid}, timeout=600)
        if not r.ok:
            # Fallback: explicit Aivis Hub download URL
            hub_url = (
                f"https://hub.aivis-project.com/api/v1/aivm-models/{uuid}"
                "/download"
            )
            r2 = requests.post(
                url, params={"url": hub_url}, timeout=600
            )
            if not r2.ok:
                raise AivisTTSError(
                    f"Failed to install voice model {uuid}: "
                    f"{r.status_code} / {r2.status_code}"
                )
        logger.info("Voice model installed: %s", uuid)

    def _is_installed(self, uuid: str) -> bool:
        try:
            r = requests.get(f"{self.engine_url}/aivm_models", timeout=10)
            if r.ok:
                models = r.json()
                return any(m.get("manifest", {}).get("uuid") == uuid for m in models.values()) \
                    or uuid in models
        except requests.RequestException:
            pass
        return False

    def resolve_style_id(
        self, model_uuid: str | None = None, style_name: str | None = None
    ) -> int:
        """Find the speaker (style) id for the configured voice."""
        if self._style_id is not None:
            return self._style_id

        model_uuid = model_uuid or CONFIG.voice_model_uuid
        style_name = style_name or CONFIG.voice_style_name

        r = requests.get(f"{self.engine_url}/speakers", timeout=15)
        r.raise_for_status()
        speakers = r.json()

        # Try matching by AIVM model UUID first, then by style name fallback.
        for sp in speakers:
            sp_uuid = sp.get("speaker_uuid") or sp.get("uuid")
            for style in sp.get("styles", []):
                # Some engines expose the AIVM uuid on style; otherwise rely on
                # the speaker's UUID.
                if sp_uuid == model_uuid or style.get("uuid") == model_uuid:
                    if style.get("name") == style_name or style_name == "":
                        self._style_id = int(style["id"])
                        logger.info(
                            "Resolved style id=%s (%s / %s)",
                            self._style_id,
                            sp.get("name"),
                            style.get("name"),
                        )
                        return self._style_id

        # Fallback: first style of the first speaker that has the UUID.
        for sp in speakers:
            sp_uuid = sp.get("speaker_uuid") or sp.get("uuid")
            if sp_uuid == model_uuid and sp.get("styles"):
                self._style_id = int(sp["styles"][0]["id"])
                logger.warning(
                    "Style '%s' not found; using first style id=%s",
                    style_name,
                    self._style_id,
                )
                return self._style_id

        raise AivisTTSError(
            f"Could not resolve a style id for model {model_uuid}. "
            f"Confirm the model is installed via tools/install_voice.py."
        )

    def synthesize(self, text: str, output_path: Path) -> Path:
        """Synthesize text -> WAV file."""
        if self._fallback:
            return self._synthesize_open_jtalk(text, output_path)
        speaker = self.resolve_style_id()

        # 1. audio_query
        q = requests.post(
            f"{self.engine_url}/audio_query",
            params={"text": text, "speaker": speaker},
            timeout=60,
        )
        q.raise_for_status()
        query = q.json()

        # Light tuning: slightly slower speech for clarity in TikTok shorts.
        query["speedScale"] = float(query.get("speedScale", 1.0)) * 1.0
        query["volumeScale"] = float(query.get("volumeScale", 1.0)) * 1.0
        query["outputSamplingRate"] = 44100

        # 2. synthesis
        s = requests.post(
            f"{self.engine_url}/synthesis",
            params={"speaker": speaker},
            json=query,
            timeout=300,
        )
        s.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(s.content)
        return output_path

    def _synthesize_open_jtalk(self, text: str, output_path: Path) -> Path:
        """Local fallback using the Open JTalk CLI."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "open_jtalk",
            "-x",
            OPEN_JTALK_DICT,
            "-m",
            OPEN_JTALK_VOICE,
            "-ow",
            str(output_path),
            "-s",
            "48000",
            "-r",
            "1.0",
            "-fm",
            "0.5",  # slight pitch lift for clarity
        ]
        proc = subprocess.run(
            cmd, input=text, text=True, capture_output=True, check=False
        )
        if proc.returncode != 0 or not output_path.exists():
            raise AivisTTSError(
                f"Open JTalk failed: rc={proc.returncode} {proc.stderr}"
            )
        # Normalize loudness to ~ -16 LUFS via ffmpeg (consistency for compose).
        normalized = output_path.with_suffix(".norm.wav")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(output_path),
                "-af",
                "loudnorm=I=-16:LRA=11:TP=-1.5,aresample=44100",
                "-ac",
                "1",
                str(normalized),
            ],
            check=True,
            capture_output=True,
        )
        normalized.replace(output_path)
        return output_path
