"""Daily limits per person on the features that use the shared free AI quota (Gemini, Groq).

One heavy user must not use up everyone's share. Counters live in the store (Redis, or memory without Redis) and
reset each day. `spend` raises a plain 429, `try_spend` just says yes or no so a feature can fall back instead.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from . import store

LIMITS = {
    "upload": int(os.getenv("UPLOAD_DAILY_LIMIT", "30")),
    "doctor_ai": int(os.getenv("DOCTOR_AI_DAILY_LIMIT", "60")),
    "review": int(os.getenv("REVIEW_DAILY_LIMIT", "40")),
}
_WORDS = {"upload": "uploads", "doctor_ai": "doctor searches", "review": "AI reviews"}


def today_ist() -> str:
    """The day limits reset on: India's calendar day, the same on every server whatever its clock zone."""
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date().isoformat()


def try_spend(actor: str, feature: str) -> bool:
    n = store.incr(f"budget:{feature}:{actor}:{today_ist()}", ttl=90000)   # atomic across API copies
    return n <= LIMITS.get(feature, 50)


def spend(actor: str, feature: str) -> None:
    if not try_spend(actor, feature):
        raise HTTPException(429, f"You have reached today's limit for {_WORDS.get(feature, feature)}. It resets tomorrow.")
