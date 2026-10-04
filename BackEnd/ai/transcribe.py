"""Speech to text for the doctor console, using Whisper on Groq.

The browser sends short audio clips, one sentence each (cut at pauses). This turns one clip into clean text:

- Whisper large-v3 is much better than the browser engine on Indian accents, drug names and Malayalam/English mixing.
- A short word list (the patient's own medicines) nudges Whisper toward the right spellings.
- Whisper invents text on silence or noise ("Thank you.", "Thanks for watching"). We read the confidence of each
  segment and drop those, so noise never becomes a transcript line.

Nothing here keeps audio. It goes to Groq and is discarded, and text is never logged.
"""
from __future__ import annotations

import os
import re
from typing import Any

from groq import Groq

MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3")
TIMEOUT_S = 30.0

# Whisper's well-known phantom phrases on silence / room noise.
_PHANTOM = {
    "thank you", "thanks", "thanks for watching", "thank you for watching", "you", "bye", "okay",
    "subtitles by the amara.org community", "please subscribe", "mm", "hmm", "uh", "um",
}


class TranscribeError(Exception):
    """A problem with a plain message that is safe to show the user."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _client() -> Groq:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise TranscribeError("Voice transcription is not set up on this server yet (the Groq key is missing).", 503)
    # max_retries=0 because clips upload in order and a hidden retry-after wait would stall every clip behind it.
    return Groq(api_key=key, timeout=TIMEOUT_S, max_retries=0)


def _get(obj: Any, name: str, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z ]+", "", (text or "").lower()).strip()


# Sentences Whisper makes up on quiet or noisy clips (it learned them from subtitles): thanks, goodbyes, sign-offs.
_INVENTED = re.compile(r"^(thanks?( you)?( so much| very much)?( for (watching|listening|your time|your attention|having me|the (help|video)))?[ ,.!]*"
                       r"([a-z]+)?|i would like to thank you( for your (time|attention))?|you'?re welcome|see you( (soon|later|next time))?|"
                       r"bye( bye)?|good ?bye|please (like|subscribe).*|thank you,? (doctor|sir|madam|jonathan|everyone))[ .!]*$", re.I)


def _invented(text: str) -> bool:
    return len(text.split()) <= 10 and bool(_INVENTED.match(text.strip()))


def _keep_segment(seg: Any) -> bool:
    """Standard Whisper checks: no speech plus low confidence, or runaway repetition."""
    text = (_get(seg, "text") or "").strip()
    if not text:
        return False
    if _norm(text) in _PHANTOM or _invented(text):
        return False
    no_speech = _get(seg, "no_speech_prob", 0.0) or 0.0
    logprob = _get(seg, "avg_logprob", 0.0) or 0.0
    compression = _get(seg, "compression_ratio", 0.0) or 0.0
    if (no_speech > 0.45 and logprob < -0.8) or logprob < -1.6:
        return False
    if compression > 2.4:
        return False
    return True


def build_prompt(vocab: list[str] | None) -> str:
    """Only a spelling list. A prompt written as a sentence ("doctor and patient talking...") makes Whisper echo or
    invent sentences on quiet clips, so we don't use one. With no medicines to bias toward, no prompt is sent.
    """
    from .medterms import common_brands  # local import: medterms reads the drug datasets on first use

    words = [w.strip() for w in (vocab or []) if w and w.strip()] + common_brands(10)
    return ("Medicines: " + ", ".join(dict.fromkeys(words))[:180] + ".") if words else ""


def transcribe(data: bytes, filename: str = "clip.webm", mime: str = "audio/webm",
               language: str | None = None, vocab: list[str] | None = None) -> dict:
    """Transcribes one clip. Returns {"text", "language", "dropped"}. Empty text means nothing real was heard."""
    client = _client()
    kwargs: dict[str, Any] = dict(
        file=(filename, data, mime),
        model=MODEL,
        response_format="verbose_json",
        temperature=0.0,
    )
    if prompt := build_prompt(vocab):
        kwargs["prompt"] = prompt
    if language:
        kwargs["language"] = language  # just a hint, leave it out to let Whisper detect the language
    from app import breaker
    try:
        with breaker.guard("groq:whisper"):
            r = client.audio.transcriptions.create(**kwargs)
    except breaker.BreakerOpen:
        raise TranscribeError("Voice transcription is paused for a moment because the service kept failing. Type the line instead, or try again shortly.", 503)
    except Exception as e:  # network, quota, bad audio
        name = type(e).__name__
        code = getattr(e, "status_code", None)
        print(f"[transcribe] Groq call failed: {name} status={code}")
        if code == 429:
            raise TranscribeError("Voice transcription has hit its free limit for now. Type the line instead, or try again shortly.", 503)
        if code in (400, 413, 415, 422):
            raise TranscribeError("That audio clip could not be read.", 422)
        raise TranscribeError("Voice transcription is not reachable right now.", 502)

    segments = _get(r, "segments") or []
    if segments:
        kept = [s for s in segments if _keep_segment(s)]
        text = " ".join((_get(s, "text") or "").strip() for s in kept).strip()
        dropped = len(segments) - len(kept)
    else:  # no segment detail came back, use the plain text and only do the phantom check
        raw = (_get(r, "text") or "").strip()
        text = "" if (_norm(raw) in _PHANTOM or _invented(raw)) else raw
        dropped = 0 if text else (1 if raw else 0)
    return {"text": re.sub(r"\s+", " ", text), "language": _get(r, "language"), "dropped": dropped}
