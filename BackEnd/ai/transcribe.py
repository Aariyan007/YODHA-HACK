"""Speech to text for the doctor console, using Groq-hosted Whisper.

The browser sends short, sentence-sized audio clips (cut at pauses). This module turns one clip
into clean text:

- Whisper `large-v3` is far better than the browser engine on Indian accents, drug names and
  Malayalam / English mixing.
- A short vocabulary prompt (the patient's own medicines) biases Whisper toward the right spellings.
- Whisper is known to invent text on silence or noise ("Thank you.", "Thanks for watching").
  We read the per-segment confidence and drop those segments, so noise never becomes a transcript line.

Nothing here keeps audio. Audio bytes are sent to Groq and discarded; text is never logged.
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
    """A problem with a plain-language message that is safe to show to the user."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _client() -> Groq:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise TranscribeError("Voice transcription is not set up on this server yet (the Groq key is missing).", 503)
    # max_retries=0: clips are uploaded in order; a hidden retry-after wait would stall every clip behind it.
    return Groq(api_key=key, timeout=TIMEOUT_S, max_retries=0)


def _get(obj: Any, name: str, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z ]+", "", (text or "").lower()).strip()


# Sentences Whisper invents on quiet or noisy clips (it learned them from subtitles): thanks, goodbyes, sign-offs.
_INVENTED = re.compile(r"^(thanks?( you)?( so much| very much)?( for (watching|listening|your time|your attention|having me|the (help|video)))?[ ,.!]*"
                       r"([a-z]+)?|i would like to thank you( for your (time|attention))?|you'?re welcome|see you( (soon|later|next time))?|"
                       r"bye( bye)?|good ?bye|please (like|subscribe).*|thank you,? (doctor|sir|madam|jonathan|everyone))[ .!]*$", re.I)


def _invented(text: str) -> bool:
    return len(text.split()) <= 10 and bool(_INVENTED.match(text.strip()))


def _keep_segment(seg: Any) -> bool:
    """Standard Whisper reliability checks: no-speech + low confidence, or runaway repetition."""
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
    """Only a spelling list. A prompt written as a sentence ("doctor and patient talking...") makes Whisper echo or invent
    sentences on quiet clips, so none is used; with no medicines to bias toward, no prompt is sent at all."""
    from .medterms import common_brands  # local import: medterms reads the drug datasets on first use

    words = [w.strip() for w in (vocab or []) if w and w.strip()] + common_brands(10)
    return ("Medicines: " + ", ".join(dict.fromkeys(words))[:180] + ".") if words else ""


def transcribe(data: bytes, filename: str = "clip.webm", mime: str = "audio/webm",
               language: str | None = None, vocab: list[str] | None = None) -> dict:
    """Transcribe one clip. Returns {"text", "language", "dropped"}. Empty text means 'nothing real heard'."""
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
        kwargs["language"] = language  # a hint only; omit to let Whisper detect it
    try:
        r = client.audio.transcriptions.create(**kwargs)
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
    else:  # model returned no segment detail; fall back to the plain text with the phantom check only
        raw = (_get(r, "text") or "").strip()
        text = "" if (_norm(raw) in _PHANTOM or _invented(raw)) else raw
        dropped = 0 if text else (1 if raw else 0)
    return {"text": re.sub(r"\s+", " ", text), "language": _get(r, "language"), "dropped": dropped}
