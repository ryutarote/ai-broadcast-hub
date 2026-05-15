"""AivisSpeech Engine TTS client.

Talks to a locally running AivisSpeech Engine (VOICEVOX-compatible HTTP API)
to synthesize Japanese speech with the ろてじん Style-Bert-VITS2 model.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

from .config import CONFIG

logger = logging.getLogger(__name__)


class AivisTTSError(RuntimeError):
    pass


class AivisTTS:
    def __init__(self, engine_url: str | None = None) -> None:
        self.engine_url = (engine_url or CONFIG.engine_url).rstrip("/")
        self._style_id: int | None = None

    def wait_until_ready(self, timeout_sec: int = 120) -> None:
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
        raise AivisTTSError(
            f"AivisSpeech Engine did not become ready within {timeout_sec}s "
            f"at {self.engine_url}"
        )

    def install_model(self, uuid: str | None = None) -> None:
        """Install the AIVM model on the engine. Idempotent."""
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
