"""Audio in, text out: `transcribe(audio, language)`.

Engine order: ElevenLabs Scribe (best for Malayalam and English mixing) if ELEVENLABS_API_KEY is set, otherwise Groq Whisper.
The transcript is only text for the person to read and edit, it never creates a medical fact by itself. Audio goes to
the engine and is discarded here, nothing is stored and text isn't logged.
"""
from __future__ import annotations

import os
import re

import httpx

from ai import transcribe as whisper

MODEL = os.getenv("ELEVENLABS_STT_MODEL", "scribe_v1")
URL = "https://api.elevenlabs.io/v1/speech-to-text"
LANG3 = {"en": "eng", "ml": "mal", "hi": "hin", "ta": "tam"}  # Scribe takes ISO 639-3, unknown or "auto" lets it detect


class SpeechError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def engine() -> str:
    return "elevenlabs" if os.getenv("ELEVENLABS_API_KEY") else "whisper" if os.getenv("GROQ_API_KEY") else "none"


def _phantom(text: str) -> bool:
    return re.sub(r"[^a-z ]+", "", text.lower()).strip() in whisper._PHANTOM


def transcribe(audio: bytes, filename: str, mime: str, language: str | None = None) -> dict:
    """Returns {"text", "language", "engine"}. text is "" for silence or noise. Raises SpeechError with a message safe to show.
    ElevenLabs goes first. If it's refused, busy or unreachable and a Groq key exists, Whisper answers instead.
    """
    eng = engine()
    if eng == "none":
        raise SpeechError("Voice is not set up on this server yet.", 503)
    if eng == "elevenlabs":
        from . import breaker
        try:
            with breaker.guard("elevenlabs"):
                return _eleven(audio, filename, mime, language)
        except (SpeechError, breaker.BreakerOpen) as e:
            if not os.getenv("GROQ_API_KEY"):
                raise e if isinstance(e, SpeechError) else SpeechError("The speech service is paused for a moment. Please try again shortly.", 503)
    try:
        out = whisper.transcribe(audio, filename, mime, language or None, [])
    except whisper.TranscribeError as e:
        raise SpeechError(str(e), e.status)
    return {"text": out.get("text", ""), "language": out.get("language"), "engine": "whisper"}


def _eleven(audio: bytes, filename: str, mime: str, language: str | None) -> dict:
    if True:
        data = {"model_id": MODEL, "tag_audio_events": "false", "diarize": "false"}
        if language and language in LANG3:
            data["language_code"] = LANG3[language]
        try:
            r = httpx.post(URL, headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}, data=data,
                           files={"file": (filename, audio, mime)}, timeout=40)
        except httpx.HTTPError:
            raise SpeechError("I could not reach the speech service. Please try again.", 502)
        if r.status_code in (401, 403):
            raise SpeechError("The speech service key was refused.", 503)
        if r.status_code == 429:
            raise SpeechError("The speech service is busy. Please try again in a moment.", 429)
        if r.status_code >= 400:
            raise SpeechError("I could not turn that into text. Please try again.", 502)
        j = r.json()
        text = (j.get("text") or "").strip()
        return {"text": "" if _phantom(text) else text, "language": j.get("language_code"), "engine": "elevenlabs"}
