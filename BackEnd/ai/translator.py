"""Groq-based patient-friendly summary + Malayalam translation."""
from __future__ import annotations

import os

from groq import Groq

MODEL = "openai/gpt-oss-120b"  # llama-3.3-70b-versatile is no longer on Groq
TIMEOUT_S = 25.0


def _client() -> Groq:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set.")
    return Groq(api_key=key, timeout=TIMEOUT_S)


def _complete(prompt: str, system: str) -> str:
    client = _client()
    kwargs = dict(
        model=MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        max_tokens=1500,
        temperature=0.3,
    )
    # gpt-oss models burn tokens on hidden reasoning. Turn it down so the
    # visible content isn't truncated.
    from app import breaker
    with breaker.guard(f"groq:{MODEL}"):
        try:
            r = client.chat.completions.create(**kwargs, reasoning_effort="low")
        except TypeError:
            r = client.chat.completions.create(**kwargs)
    out = (r.choices[0].message.content or "").strip()
    if not out and r.choices[0].finish_reason == "length":
        # Reasoning used up the budget, retry without reasoning or with a bigger budget.
        kwargs["max_tokens"] = 3000
        r = client.chat.completions.create(**kwargs)
        out = (r.choices[0].message.content or "").strip()
    return out


def summarise(doc: dict, alerts: list[dict]) -> dict:
    """Returns {"en": ..., "ml": ...}. Falls back gracefully if Groq fails."""
    bullets = []
    if doc.get("hospital") or doc.get("doctor"):
        bullets.append(f"Place / doctor: {doc.get('hospital') or ''} {doc.get('doctor') or ''}".strip())
    if doc.get("diagnoses"):
        bullets.append("Diagnoses / notes: " + ", ".join(doc["diagnoses"]))
    for m in doc.get("medicines", []):
        bullets.append(f"Medicine: {m.get('name', '')} {m.get('dose', '')} {m.get('schedule', '')} {('for ' + m['purpose']) if m.get('purpose') else ''}".strip())
    for o in doc.get("observations", []):
        bullets.append(f"{o.get('name', '')}: {o.get('value', '')} {o.get('unit', '')} (range {o.get('range', '')})")
    if doc.get("follow_up"):
        bullets.append("Follow-up: " + doc["follow_up"])
    for a in alerts:
        bullets.append(f"Warning: {a['title']}")

    joined = "\n".join(f"- {b}" for b in bullets if b)

    system = (
        "You are a careful medical scribe writing for an Indian elderly patient with no medical training. "
        "Write only what the document says. Never diagnose. Keep medicine names and numbers unchanged. "
        "Three or four short sentences. Simple English."
    )
    user = f"Document facts:\n{joined}\n\nWrite a short, kind summary for the patient."

    try:
        en = _complete(user, system)
    except Exception as e:
        print(f"[translator] English summary failed: {type(e).__name__}: {e}")
        en = ""
    if not en.strip():
        en = (
            " ".join(bullets[:3]) if bullets else "The document was added to your records. Please discuss it with your doctor."
        )

    system_ml = (
        "You translate English medical summaries into simple, conversational Malayalam for an elderly patient. "
        "Keep every medicine name, number, and dose exactly as in the English text (do not transliterate). "
        "Keep it short and kind. Reply with Malayalam only, no quotes, no English."
    )
    try:
        ml = _complete(en, system_ml)
    except Exception as e:
        print(f"[translator] Malayalam translation failed: {type(e).__name__}: {e}")
        ml = en

    return {"en": en, "ml": ml}
