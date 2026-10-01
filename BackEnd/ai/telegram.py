"""Fire-and-forget Telegram notifications. Any failure is logged and swallowed."""
from __future__ import annotations

import os

import httpx

TIMEOUT_S = 4.0


def notify(message: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=TIMEOUT_S) as cx:
            r = cx.post(url, data={"chat_id": chat, "text": message})
        if r.status_code != 200:
            print(f"[telegram] HTTP {r.status_code}")
            return False
        return True
    except Exception as e:
        print(f"[telegram] failed: {type(e).__name__}")
        return False
