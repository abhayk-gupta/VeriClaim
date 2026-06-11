"""
Whisper speech-to-text wrapper (local, free).

Used to transcribe the customer's recorded answer during an outbound
clarification call. The model is loaded lazily and cached process-wide.

For inbound IVR turns we rely on Twilio's `<Gather input="speech">` (SpeechResult),
which is included in the per-minute call cost — Whisper is only needed for
recorded audio (the clarification-call answer).
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_model = None


def _get_model():
    global _model
    if _model is None:
        import whisper

        logger.info("Loading Whisper model: %s", settings.whisper_model)
        _model = whisper.load_model(settings.whisper_model, device=settings.whisper_device)
    return _model


def transcribe_file(path: str | Path) -> str:
    result = _get_model().transcribe(str(path), fp16=False)
    text = (result.get("text") or "").strip()
    logger.info("Transcribed %s (%d chars)", path, len(text))
    return text


def transcribe_bytes(audio: bytes, suffix: str = ".wav") -> str:
    """Write bytes to a temp file and transcribe (Whisper reads from disk via ffmpeg)."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio)
        tmp_path = tmp.name
    try:
        return transcribe_file(tmp_path)
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass


def is_enabled() -> Optional[bool]:
    return settings.use_local_whisper
