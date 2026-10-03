"""Daily limits per person on the features that use the shared free AI quota (Gemini, Groq).

One heavy user must not use up everyone's share. Counters live in the store (Redis, or memory without Redis) and
reset each day. `spend` raises a plain 429, `try_spend` just says yes or no so a feature can fall back instead.
"""
from __future__ import annotations

import os
from datetime import date

from fastapi import HTTPException

from . import store

LIMITS = {
    "upload": int(os.getenv("UPLOAD_DAILY_LIMIT", "30")),
    "doctor_ai": int(os.getenv("DOCTOR_AI_DAILY_LIMIT", "60")),
    "review": int(os.getenv("REVIEW_DAILY_LIMIT", "40")),
}
_WORDS = {"upload": "uploads", "doctor_ai": "doctor searches", "review": "AI reviews"}


def try_spend(actor: str, feature: str) -> bool:
    key = f"budget:{feature}:{actor}:{date.today().isoformat()}"
    n = int(store.get_value(key) or 0) + 1
    store.set_value(key, str(n), ttl=90000)
    return n <= LIMITS.get(feature, 50)


def spend(actor: str, feature: str) -> None:
    if not try_spend(actor, feature):
        raise HTTPException(429, f"You have reached today's limit for {_WORDS.get(feature, feature)}. It resets tomorrow.")
