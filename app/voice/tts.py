"""
Piper text-to-speech wrapper (offline, free).

Generates a .wav file from text using the local Piper voice model, cached on
disk by a hash of the text so repeated prompts are synthesized once. Served to
Twilio via the `/webhooks/voice/audio/{filename}` endpoint with the `<Play>` verb.

Piper is an OPTIONAL enhancement: the TwiML builders default to Twilio's built-in
`<Say>` (no model download required). Use Piper when you want a consistent custom
voice and have run `scripts/download_piper_model.sh`. `is_available()` lets callers
fall back gracefully.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_AUDIO_DIR = Path("audio")
_voice = None


def is_available() -> bool:
    return Path(settings.piper_model_path).exists()


def _get_voice():
    global _voice
    if _voice is None:
        from piper.voice import PiperVoice

        _voice = PiperVoice.load(settings.piper_model_path)
    return _voice


def _filename_for(text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    return f"tts_{digest}.wav"


def synthesize(text: str) -> str:
    """Synthesize `text` to a cached wav and return its filename (not full path)."""
    if not is_available():
        raise RuntimeError(
            f"Piper model not found at {settings.piper_model_path}. "
            "Run scripts/download_piper_model.sh or use <Say> instead."
        )

    _AUDIO_DIR.mkdir(exist_ok=True)
    filename = _filename_for(text)
    out_path = _AUDIO_DIR / filename
    if out_path.exists():
        return filename

    import wave

    voice = _get_voice()
    with wave.open(str(out_path), "wb") as wav_file:
        voice.synthesize(text, wav_file)
    logger.info("Synthesized TTS prompt -> %s", filename)
    return filename


def audio_path(filename: str) -> Path:
    return _AUDIO_DIR / filename
