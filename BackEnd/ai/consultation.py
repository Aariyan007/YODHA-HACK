"""Groq helpers for the live consultation.

Does three things:
1. builds a rough SOAP note from the transcript (every 3 lines)
2. suggests up to 3 questions the doctor hasn't asked yet
3. builds the final SOAP note at finalize, with the source line numbers

Every call has a 25 s timeout. If something fails we return an empty result instead of raising.
Nothing here diagnoses, it only repeats what the doctor said.
"""
from __future__ import annotations

import json
import os
from typing import Any

from groq import Groq

MODEL = "openai/gpt-oss-120b"
FALLBACK_MODEL = "openai/gpt-oss-20b"  # own quota, used when MODEL is rate limited (finalize only)
TIMEOUT_S = 25.0

EMPTY_SOAP = {"subjective": None, "objective": None, "assessment": None, "plan": None}


def _client() -> Groq:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set.")
    # max_retries=0 because the SDK would retry a rate limited call twice and wait on retry-after,
    # which can hang the request for a minute (nginx then gives a 504). Fail fast and use the fallback.
    return Groq(api_key=key, timeout=TIMEOUT_S, max_retries=0)


def _is_limit(e: Exception) -> bool:
    # an open circuit breaker is treated like a rate limit: skip to the fallback model, never wait it out
    return type(e).__name__ in ("RateLimitError", "BreakerOpen")


def _retry_after(e: Exception) -> float | None:
    try:
        return float(e.response.headers.get("retry-after"))  # type: ignore[attr-defined]
    except Exception:
        return None


def _chat_json(system: str, user: str, max_tokens: int = 900, wait_on_limit: float = 0.0,
               fallback_model: str | None = None) -> dict[str, Any] | None:
    """One JSON-mode Groq call. Returns a dict, or None if anything fails.
    
    Free tier limits are 8,000 tokens/min and 200,000/day per model, so:
    - fallback_model: if the main model is rate limited, try this one straight away (own quota).
    - wait_on_limit: if Groq says the wait is short (per-minute limit), wait and try the main model once more.
      A daily limit is never waited out.
    Live per-line calls set neither, so the doctor's screen never hangs.
    """
    try:
        return _chat_json_once(system, user, max_tokens)
    except Exception as e:
        if not _is_limit(e):
            print(f"[consultation] JSON call failed: {type(e).__name__}")
            return None
        first = e
    if fallback_model:
        try:
            out = _chat_json_once(system, user, max_tokens, model=fallback_model)
            print(f"[consultation] used {fallback_model}: {MODEL} is rate-limited")
            return out
        except Exception as e2:
            if not _is_limit(e2):
                print(f"[consultation] fallback model failed: {type(e2).__name__}")
                return None
    after = _retry_after(first)
    if wait_on_limit and after is not None and after <= wait_on_limit:
        import time
        time.sleep(max(after, 1.0))
        try:
            return _chat_json_once(system, user, max_tokens)
        except Exception as e3:
            print(f"[consultation] JSON call failed after wait: {type(e3).__name__}")
            return None
    print("[consultation] JSON call failed: RateLimitError")
    return None


def _chat_json_once(system: str, user: str, max_tokens: int, model: str | None = None) -> dict[str, Any] | None:
    """One JSON-mode Groq call. Raises on API errors so the caller can wait and retry."""
    client = _client()
    kwargs = dict(
        model=model or MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    from app import breaker
    with breaker.guard(f"groq:{kwargs['model']}"):
        try:
            r = client.chat.completions.create(**kwargs, reasoning_effort="low")
        except TypeError:
            r = client.chat.completions.create(**kwargs)
    try:
        from app import tokens
        tokens.record("json-calls", model or MODEL, getattr(r, "usage", None))  # consultation, visit classification, agent planner fallback
    except Exception:
        pass
    text = (r.choices[0].message.content or "").strip()
    if not text:
        return None
    return json.loads(text)


def _lines_block(lines: list[dict]) -> str:
    """Turn the transcript into numbered lines so the model can point at them."""
    return "\n".join(f"[{i}] {ln.get('speaker', '?')}: {ln.get('text', '')}" for i, ln in enumerate(lines))


# ---------- partial SOAP (called every 3 lines) ----------

_PARTIAL_SYSTEM = (
    "You are a careful medical scribe helping a doctor during a live visit. "
    "Build a partial SOAP note strictly from the transcript shown. "
    "Reply as ONE JSON object with keys 'subjective', 'objective', 'assessment', 'plan'. "
    "Each value is a short string or null. Fill a field only when the transcript clearly supports it. "
    "ASSESSMENT must only restate what the DOCTOR explicitly said. If the doctor did not state an "
    "assessment, assessment MUST be null. Never diagnose on your own. Never invent medicines. "
    "Ignore greetings, small talk and any chat that is not about the patient's health. "
    "Keep each field under two sentences. Do not include any extra keys."
)


def partial_soap(lines: list[dict]) -> dict:
    """Gives back {subjective, objective, assessment, plan}. Empty if the call fails."""
    if not lines:
        return dict(EMPTY_SOAP)
    out = _chat_json(_PARTIAL_SYSTEM, _lines_block(lines), max_tokens=500)
    if not isinstance(out, dict):
        return dict(EMPTY_SOAP)
    return {k: out.get(k) if isinstance(out.get(k), (str, type(None))) else None for k in EMPTY_SOAP}


# ---------- follow-up question suggestions ----------

_QUESTIONS_SYSTEM = (
    "You are an assistant for a doctor during a live patient visit. "
    "Suggest up to THREE short follow-up questions the doctor has NOT yet asked, "
    "to clarify history or safety. Prefer: symptom duration, severity, allergies, "
    "medicine adherence, red-flag symptoms (chest pain, breathlessness, weight loss). "
    "Reply as ONE JSON object: {\"questions\": [\"q1\", \"q2\", \"q3\"]}. "
    "If nothing useful remains, return an empty list. Do NOT suggest a diagnosis."
)


def suggest_questions(lines: list[dict], patient_summary: dict) -> list[str]:
    if not lines:
        return []
    ctx = (
        f"Patient conditions: {', '.join(patient_summary.get('conditions') or []) or 'none listed'}\n"
        f"Known allergies: {', '.join(patient_summary.get('allergies') or []) or 'none listed'}\n"
        f"Active medicines: {', '.join(patient_summary.get('medicines') or []) or 'none listed'}\n\n"
        f"Transcript so far:\n{_lines_block(lines)}"
    )
    out = _chat_json(_QUESTIONS_SYSTEM, ctx, max_tokens=350)
    if not isinstance(out, dict):
        return []
    qs = out.get("questions") or []
    return [q for q in qs if isinstance(q, str) and q.strip()][:3]


# ---------- final SOAP (at /finalize) ----------

_FINAL_SYSTEM = (
    "You are a careful medical scribe writing the final SOAP note for a visit. "
    "Use ONLY the transcript provided. Each line is prefixed with its index like '[0] doctor: ...'. "
    "Reply as ONE JSON object with keys subjective, objective, assessment, plan. "
    "Each value is itself an object {\"text\": string, \"source_lines\": [int, ...]} where "
    "source_lines lists the transcript indexes that support the text. "
    "ASSESSMENT.text may only restate what the DOCTOR said in the transcript. "
    "If the doctor stated no assessment, use {\"text\": null, \"source_lines\": []} for assessment. "
    "Never invent medicines; include only ones the doctor actually prescribed. "
    "Ignore greetings, small talk and any chat that is not about the patient's health. "
    "Keep each 'text' two to four short sentences. Return no extra keys."
)


def final_soap(lines: list[dict], retry: bool = True) -> dict:
    """SOAP note with source line numbers per field. Retries once if the output is broken."""
    if not lines:
        return _empty_final()
    out = _chat_json(_FINAL_SYSTEM, _lines_block(lines), max_tokens=1200, wait_on_limit=8.0, fallback_model=FALLBACK_MODEL)
    if not _looks_final(out) and retry:
        out = _chat_json(_FINAL_SYSTEM, _lines_block(lines), max_tokens=1500, wait_on_limit=8.0, fallback_model=FALLBACK_MODEL)
    if not _looks_final(out):
        return _empty_final()
    return _normalise_final(out, max_idx=len(lines) - 1)


def _empty_final() -> dict:
    return {k: {"text": None, "source_lines": []} for k in ("subjective", "objective", "assessment", "plan")}


def _looks_final(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    return all(k in obj for k in ("subjective", "objective", "assessment", "plan"))


def _normalise_final(obj: dict, max_idx: int) -> dict:
    out = _empty_final()
    for k in out:
        v = obj.get(k)
        if isinstance(v, dict):
            txt = v.get("text")
            src = v.get("source_lines")
        elif isinstance(v, str):
            txt, src = v, []
        else:
            txt, src = None, []
        if not isinstance(txt, (str, type(None))):
            txt = None
        if not isinstance(src, list):
            src = []
        src = [int(x) for x in src if isinstance(x, (int, float)) and 0 <= int(x) <= max_idx]
        out[k] = {"text": txt, "source_lines": src}
    return out


# ---------- speaker guess ----------

def guess_speaker(text: str) -> str:
    """Quick guess: a line that looks like a question is the doctor, anything else is the patient."""
    t = (text or "").strip()
    if not t:
        return "patient"
    if "?" in t:
        return "doctor"
    low = t.lower()
    if low.startswith(("do you", "have you", "are you", "when", "how", "why", "where", "any ", "did ")):
        return "doctor"
    return "patient"


# ---------- patient-facing summary (en + ml) ----------

_SUMMARY_SYSTEM_EN = (
    "You are a medical scribe writing a short patient-facing summary of a doctor's visit. "
    "Use ONLY the SOAP note given. Three or four simple sentences. Never diagnose beyond what "
    "the doctor stated. Keep medicine names and numbers exactly. Reply with plain text only."
)
_SUMMARY_SYSTEM_ML = (
    "Translate the English visit summary into simple conversational Malayalam for an elderly patient. "
    "Keep every medicine name, number and dose exactly as in English. Reply with Malayalam only, "
    "no English, no quotes."
)


def patient_summary(final_note: dict) -> dict:
    """Return {en, ml}. Falls back to a plain join if Groq fails."""
    bits = []
    for k in ("subjective", "objective", "assessment", "plan"):
        v = (final_note.get(k) or {}).get("text")
        if v:
            bits.append(f"{k.title()}: {v}")
    joined = "\n".join(bits) or "Visit was recorded."
    try:
        client = _client()
        kwargs = dict(
            model=MODEL,
            messages=[{"role": "system", "content": _SUMMARY_SYSTEM_EN}, {"role": "user", "content": joined}],
            max_tokens=600, temperature=0.2,
        )
        from app import breaker
        with breaker.guard(f"groq:{MODEL}"):
            try:
                r = client.chat.completions.create(**kwargs, reasoning_effort="low")
            except TypeError:
                r = client.chat.completions.create(**kwargs)
        en = (r.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[consultation] EN summary failed: {type(e).__name__}")
        en = ""
    if not en:
        en = joined

    try:
        client = _client()
        kwargs = dict(
            model=MODEL,
            messages=[{"role": "system", "content": _SUMMARY_SYSTEM_ML}, {"role": "user", "content": en}],
            max_tokens=800, temperature=0.2,
        )
        from app import breaker
        with breaker.guard(f"groq:{MODEL}"):
            try:
                r = client.chat.completions.create(**kwargs, reasoning_effort="low")
            except TypeError:
                r = client.chat.completions.create(**kwargs)
        ml = (r.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[consultation] ML summary failed: {type(e).__name__}")
        ml = en
    return {"en": en, "ml": ml or en}
