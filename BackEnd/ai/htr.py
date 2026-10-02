"""Client for the optional handwriting reader (htr/, TrOCR). Returns None whenever it is off, slow or failing: it is only ever a
third reader, never required."""
from __future__ import annotations

import os
import time

import httpx

TIMEOUT = float(os.getenv("HTR_TIMEOUT_S", "25"))
_fails = 0
_open_until = 0.0


def available() -> bool:
    return bool(os.getenv("HTR_URL")) and time.time() >= _open_until


def read(image: bytes) -> list[str] | None:
    """Text lines the reader saw, or None. Three failures in a row switch it off for 5 minutes (circuit breaker)."""
    global _fails, _open_until
    if not available():
        return None
    try:
        r = httpx.post(os.environ["HTR_URL"].rstrip("/") + "/read", files={"file": ("page.png", image, "image/png")}, timeout=TIMEOUT)
        r.raise_for_status()
        _fails = 0
        return [str(l.get("text", "")).strip() for l in r.json().get("lines", []) if str(l.get("text", "")).strip()]
    except Exception:
        _fails += 1
        if _fails >= 3:
            _open_until, _fails = time.time() + 300, 0
        return None


def seen(name: str, lines: list[str]) -> bool:
    """Did the third reader see something close to this drug name? (loose: handwriting readers are noisy)"""
    import difflib
    n = "".join(c for c in name.lower() if c.isalnum())
    if len(n) < 3:
        return False
    for line in lines:
        for word in line.lower().split():
            w = "".join(c for c in word if c.isalnum())
            if w and difflib.SequenceMatcher(None, n, w).ratio() >= 0.7:
                return True
    return False
