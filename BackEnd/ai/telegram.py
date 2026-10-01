"""Telegram helpers. Failures are logged as one short line and never raise.

Never log the bot token, chat ids, or message text. Error strings returned to
callers are plain-language and token-free.
"""
from __future__ import annotations

import os

import httpx

TIMEOUT_S = 4.0


def ready() -> bool:
    return bool((os.getenv("TELEGRAM_BOT_TOKEN") or "").strip())


def send_to(chat_id: str | None, message: str) -> tuple[bool, str | None]:
    """Send `message` to `chat_id`. Returns (ok, plain_error)."""
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return False, "Telegram is not set up on the server (bot token missing)."
    if not chat_id:
        return False, "No Telegram chat ID is saved yet."
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=TIMEOUT_S) as cx:
            r = cx.post(url, data={"chat_id": str(chat_id), "text": message})
    except Exception as e:
        print(f"[telegram] send failed: {type(e).__name__}")
        return False, "Could not reach Telegram. Check the internet connection and try again."
    if r.status_code == 200:
        return True, None
    desc = ""
    try:
        desc = str(r.json().get("description") or "")
    except Exception:
        pass
    print(f"[telegram] HTTP {r.status_code}")
    low = desc.lower()
    if "chat not found" in low:
        return False, "Telegram could not find that chat ID. Message the MediThread bot first, then paste your ID."
    if "blocked" in low or "forbidden" in low:
        return False, "The MediThread bot cannot message this chat. Open the bot in Telegram and press Start."
    if r.status_code == 401:
        return False, "The server's Telegram bot token was rejected."
    return False, f"Telegram refused the message (code {r.status_code})."


def notify(message: str) -> bool:
    """Fire-and-forget message to the default TELEGRAM_CHAT_ID."""
    ok, _ = send_to(os.getenv("TELEGRAM_CHAT_ID"), message)
    return ok


def check() -> tuple[bool, str]:
    """One tiny read-only call (getMe, sends nothing). Returns (ok, plain detail). Never leaks the token."""
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return False, "Bot token is not set."
    try:
        with httpx.Client(timeout=TIMEOUT_S) as cx:
            r = cx.get(f"https://api.telegram.org/bot{token}/getMe")
    except Exception as e:
        return False, f"Could not reach Telegram ({type(e).__name__})."
    if r.status_code == 200:
        return True, "Bot is ready."
    return False, f"Telegram rejected the bot (HTTP {r.status_code})."
