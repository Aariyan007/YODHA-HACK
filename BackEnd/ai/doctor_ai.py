"""Groq helpers for the doctor finder. The ranking itself is Python (app/doctors.py).

1. parse(q): reads free text like "a Malayalam speaking heart doctor near Kakkanad open Sunday" into
   filters, limited to the specialties, languages and towns we know.
2. explain(): for the top picks, says why that doctor fits and sums up the reviews in English and Malayalam.

The model only sees doctors Python already picked and can only give back their ids.
Anything off the list is dropped and a Python template fills the gap.
"""
from __future__ import annotations

import json
import os
import re

from groq import Groq

from app.doctors import LANGUAGES, SPECIALTIES, cities

MODEL = "openai/gpt-oss-120b"
TIMEOUT_S = 20.0
_CACHE: dict[str, object] = {}

BANNED = re.compile(r"\b(diagnos|you have|cure|guarantee|best doctor in|prescribe|treat(?:s|ment) for your)\b", re.I)


def _chat_json(system: str, user: str, max_tokens: int = 1200) -> dict | None:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    try:
        client = Groq(api_key=key, timeout=TIMEOUT_S)
        kwargs = dict(model=MODEL, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                      max_tokens=max_tokens, temperature=0.2, response_format={"type": "json_object"})
        try:
            r = client.chat.completions.create(**kwargs, reasoning_effort="low")
        except TypeError:
            r = client.chat.completions.create(**kwargs)
        text = (r.choices[0].message.content or "").strip()
        return json.loads(text) if text else None
    except Exception as e:
        print(f"[doctor_ai] Groq call failed: {type(e).__name__}")
        return None


def parse(q: str) -> dict:
    """AI reading of a search. Only known values survive. Returns {} without Groq."""
    q = (q or "").strip()[:300]
    if not q:
        return {}
    ck = "parse:" + q.lower()
    if ck in _CACHE:
        return dict(_CACHE[ck])  # type: ignore[arg-type]
    towns = [c["city"] for c in cities()]
    system = (
        "You turn a patient's request for a doctor in India into search filters. Return ONLY JSON with any of these keys:\n"
        f'"specialty": one of {json.dumps(SPECIALTIES)}\n'
        f'"language": one of {json.dumps(LANGUAGES)}\n'
        f'"city": one of {json.dumps(towns)} (only if a place is named; map nearby areas to the closest town)\n'
        '"day": one of ["mon","tue","wed","thu","fri","sat","sun","today"]\n'
        '"openNow": true, "emergency": true, "teleconsult": true, "maxFee": integer rupees, "maxKm": number, "minRating": number 1-5\n'
        "Pick the specialty from the body part or problem described (chest pain or stroke signs -> Emergency). "
        "Leave out keys that are not asked for. Never add a diagnosis."
    )
    raw = _chat_json(system, q, max_tokens=400) or {}
    out: dict = {}
    if raw.get("specialty") in SPECIALTIES:
        out["specialty"] = raw["specialty"]
    if raw.get("language") in LANGUAGES:
        out["language"] = raw["language"]
    if raw.get("city") in towns:
        out["city"] = raw["city"]
    if raw.get("day") in ("mon", "tue", "wed", "thu", "fri", "sat", "sun", "today"):
        out["day"] = raw["day"]
    for flag in ("openNow", "emergency", "teleconsult"):
        if raw.get(flag) is True:
            out[flag] = True
    for k, lo, hi, cast in (("maxFee", 0, 100000, int), ("maxKm", 1, 2000, float), ("minRating", 1, 5, float)):
        try:
            v = cast(raw[k])
            if lo <= v <= hi:
                out[k] = v
        except (KeyError, TypeError, ValueError):
            pass
    _CACHE[ck] = dict(out)
    return out


def _fallback_why(d: dict, language: str | None) -> dict:
    bits = [f"{d['distanceKm']:g} km away", f"rated {d['rating']} from {d['reviews']} reviews"]
    lang = language or "Malayalam"
    if lang in d["languages"]:
        bits.append(f"speaks {lang}")
    if d.get("emergency24x7"):
        bits.append("open 24 hours with an emergency team")
    elif d.get("openNow"):
        bits.append(f"open now until {d['closesAt']}" if d.get("closesAt") else "open now")
    who = f"{d['clinic']} ({d['department']} department)" if d.get("department") else f"{d['name']} ({d['specialty']})"
    why = f"{who}: " + ", ".join(bits) + "."
    why_ml = f"{d['name']}: {d['distanceKm']:g} km അകലെ, {d['reviews']} റിവ്യൂകളിൽ നിന്ന് {d['rating']} റേറ്റിംഗ്."
    snippets = d.get("reviewSnippets") or []
    summary = f"People say: {snippets[0].rstrip('.').lower()}." if snippets else ""
    if len(snippets) > 2:
        summary += f" One worry: {snippets[-1].rstrip('.').lower()}."
    return {"id": d["id"], "why": why, "whyMl": why_ml, "reviewSummary": summary, "reviewSummaryMl": None, "source": "rules"}


def explain(picks: list[dict], context: dict) -> list[dict]:
    """Why each top pick fits, plus a review summary. Always one entry per pick."""
    picks = picks[:3]
    if not picks:
        return []
    fallback = {d["id"]: _fallback_why(d, context.get("language")) for d in picks}
    slim = [{k: d.get(k) for k in ("id", "name", "specialty", "department", "clinic", "type", "city", "distanceKm", "rating", "reviews",
                                   "reviewSnippets", "feeInr", "languages", "openNow", "closesAt", "emergency24x7",
                                   "teleconsult", "waitMinutes", "experienceYears")} for d in picks]
    ck = "explain:" + json.dumps([slim, context], sort_keys=True, default=str)
    if ck in _CACHE:
        return list(_CACHE[ck])  # type: ignore[arg-type]
    system = (
        "You help an elderly patient in Kerala choose between doctors that a ranking system has ALREADY picked. "
        "For each doctor, write one short reason (max 30 words) that uses only the facts given: distance, rating and number of "
        "reviews, language, opening hours, fee, wait time, 24-hour emergency. Mention why it fits the patient's need when "
        "a need is given. When a doctor has a \"department\", the patient will see that hospital department, so talk about the "
        "hospital and department, not the named doctor's own specialty. Then summarise the review snippets in one short line with one good point and one worry. "
        "Never diagnose, never promise results, never invent facts. Return ONLY JSON: "
        '{"picks":[{"id":"...","why":"...","whyMl":"same in simple Malayalam","reviewSummary":"...","reviewSummaryMl":"..."}]}'
    )
    user = json.dumps({"patientNeed": context, "doctors": slim}, ensure_ascii=False)
    raw = _chat_json(system, user) or {}
    ids = {d["id"] for d in picks}
    got: dict[str, dict] = {}
    for p in raw.get("picks") or []:
        if not isinstance(p, dict) or p.get("id") not in ids:
            continue
        why = p.get("why") if isinstance(p.get("why"), str) else ""
        if not why.strip() or BANNED.search(why) or len(why) > 400:
            continue
        rs = p.get("reviewSummary") if isinstance(p.get("reviewSummary"), str) and not BANNED.search(p["reviewSummary"]) else fallback[p["id"]]["reviewSummary"]
        got[p["id"]] = {"id": p["id"], "why": why.strip(),
                        "whyMl": p.get("whyMl") if isinstance(p.get("whyMl"), str) and not BANNED.search(p["whyMl"]) else None,
                        "reviewSummary": rs.strip(),
                        "reviewSummaryMl": p.get("reviewSummaryMl") if isinstance(p.get("reviewSummaryMl"), str) else None,
                        "source": "ai"}
    out = [got.get(d["id"]) or fallback[d["id"]] for d in picks]
    if got:
        _CACHE[ck] = out
    return out
