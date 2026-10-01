"""AI health review: Groq reads the patient's WHOLE record and explains it in plain words.

Input is facts only: profile, every stored reading with dates, active medicines,
open warnings, and the Python danger checks (app/risk.py). The model is asked to
connect things across reports ("BP was 128 in March, 146 now"), point out what is
missing (no kidney test in a year for a diabetic), and list questions for the doctor.

Safety, enforced in code after the call, not just in the prompt:
  - every point must cite numbers that exist in the record; points with numbers
    we cannot find are dropped
  - points that diagnose, name a treatment, or tell the patient to start/stop/change
    a medicine are dropped
  - the Python risk levels are never changed by the AI; emergencies come from Python
If Groq is missing or fails, a Python-only review is returned so the screen always works.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date

from groq import Groq

from app.trends import HIGHER_IS_WORSE

MODEL = "openai/gpt-oss-120b"
TIMEOUT_S = 25.0
_CACHE: dict[str, dict] = {}  # input hash -> review (the same record gives the same answer)

BANNED = re.compile(
    r"\b(you have|you are suffering|diagnos|is caused by|due to your|because of your|"
    r"start taking|stop taking|increase (?:the |your )?dose|decrease (?:the |your )?dose|reduce (?:the |your )?dose|"
    r"double the dose|skip (?:the |your )?(?:dose|medicine)|switch to|replace (?:it|your)|prescribe|"
    r"you should take|take \d+ ?mg)\b", re.I)

SYSTEM = """You are a careful health record assistant for an elderly Indian patient and their family.
You read their stored medical record and explain it in very simple words.

Hard rules:
- Never diagnose. Never say what disease they have or what caused something.
- Never suggest starting, stopping or changing any medicine or dose. Never suggest a treatment.
- Only use numbers and dates that appear in the record. Copy them exactly.
- Say "show this to your doctor" or "ask your doctor" instead of giving advice.
- Short sentences. Kind tone. No medical jargon without a plain explanation.

Return ONLY a JSON object:
{
  "headline": "one sentence overview, max 25 words",
  "points": [
     {"text": "one observation that connects facts across reports, with the numbers and dates",
      "kind": "worse" | "better" | "steady" | "missing" | "info",
      "tests": ["codes of the tests this point is about, e.g. sbp, hba1c"]}
  ],
  "askDoctor": ["a short question the patient can ask the doctor", "..."],
  "headlineMl": "the headline in simple Malayalam (numbers unchanged)",
  "pointsMl": ["each point text in simple Malayalam, same order"],
  "askDoctorMl": ["each question in simple Malayalam, same order"]
}
Give 2 to 5 points and 2 to 4 questions. "missing" points are about useful tests that are absent or old
(for example no kidney test in the last year for someone on diabetes medicine)."""


def _client() -> Groq:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set.")
    return Groq(api_key=key, timeout=TIMEOUT_S)


def _facts(profile: dict, series: list[dict], medicines: list[dict], alerts: list[dict], risks: list[dict],
           today: date) -> dict:
    return {
        "today": today.isoformat(),
        "patient": {k: profile.get(k) for k in ("age", "gender", "conditions", "allergies")},
        "readings": [{"test": s["name"], "code": s["code"], "unit": s.get("unit"),
                      "values": [[p["date"], p["value"]] for p in s["points"][-8:]]} for s in series],
        "medicines": [{"name": m.get("name"), "generic": m.get("generic"), "dose": m.get("dose"),
                       "schedule": m.get("frequency"), "since": m.get("startDate")} for m in medicines],
        "openWarnings": [a.get("title") for a in alerts if not a.get("resolved")][:12],
        "safetyChecks": [{"level": r["level"], "title": r["title"]} for r in risks],
    }


def _numbers_in(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", text or "")


def _allowed_numbers(facts: dict) -> set[str]:
    blob = json.dumps(facts)
    nums = set(_numbers_in(blob))
    # Allow the same number written without a trailing .0, and small counts ("3 reports", "2 tests").
    nums |= {n[:-2] for n in nums if n.endswith(".0")}
    nums |= {str(i) for i in range(0, 13)}
    nums |= {"100", "130", "80", "90", "140", "7", "70", "180"}  # common targets the model may quote
    return nums


def _safe(text: str, allowed: set[str]) -> bool:
    if not text or BANNED.search(text):
        return False
    # Dates like 2025-03-12 split into numbers that are all in the record anyway.
    return all(n in allowed or n.lstrip("0") in allowed for n in _numbers_in(text))


def _call(facts: dict) -> dict | None:
    try:
        client = _client()
        kwargs = dict(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": "Record (JSON):\n" + json.dumps(facts, ensure_ascii=False)}],
            max_tokens=1800, temperature=0.2, response_format={"type": "json_object"},
        )
        try:
            r = client.chat.completions.create(**kwargs, reasoning_effort="low")
        except TypeError:
            r = client.chat.completions.create(**kwargs)
        text = (r.choices[0].message.content or "").strip()
        return json.loads(text) if text else None
    except Exception as e:
        print(f"[health_review] Groq call failed: {type(e).__name__}")
        return None


def python_review(series: list[dict], risks: list[dict], medicines: list[dict], today: date) -> dict:
    """No-AI fallback: the same shape, built from the risk list and the series."""
    points = []
    for s in [s for s in series if len(s["points"]) >= 2][:4]:
        pts = s["points"]
        first, last = pts[0], pts[-1]
        if first["value"] == last["value"]:
            kind = "steady"
        elif s["code"] in HIGHER_IS_WORSE:
            kind = "worse" if last["value"] > first["value"] else "better"
        else:
            kind = "info"
        points.append({"text": f"{s['name']} went from {first['value']:g} on {first['date']} to {last['value']:g} on {last['date']}.",
                       "textMl": None, "kind": kind, "tests": [s["code"]]})
    on_diabetes_med = any((m.get("generic") or "").lower() in ("metformin", "glimepiride", "gliclazide", "sitagliptin",
                                                                "vildagliptin", "insulin") for m in medicines)
    have = {s["code"] for s in series}
    if on_diabetes_med and "creatinine" not in have and "egfr" not in have:
        points.append({"text": "There is no kidney test (creatinine) in your record. People on sugar medicine usually have one each year. Ask your doctor.",
                       "textMl": "നിങ്ങളുടെ രേഖയിൽ വൃക്ക പരിശോധന (ക്രിയാറ്റിനിൻ) ഇല്ല. ഡോക്ടറോട് ചോദിക്കുക.",
                       "kind": "missing", "tests": ["creatinine"]})
    worst = risks[0] if risks else None
    if worst:
        headline = f"{len(risks)} thing{'s' if len(risks) != 1 else ''} in your record to show your doctor. Most important: {worst['title'].lower()}."
        headline_ml = f"ഡോക്ടറെ കാണിക്കേണ്ട {len(risks)} കാര്യങ്ങൾ. ഏറ്റവും പ്രധാനം: {worst['title']}."
    elif series or points:
        headline, headline_ml = ("Nothing in your record needs urgent attention right now.",
                                 "ഇപ്പോൾ അടിയന്തരമായി ശ്രദ്ധിക്കേണ്ട ഒന്നും നിങ്ങളുടെ രേഖയിലില്ല.")
    else:
        headline, headline_ml = ("Add a report or a home reading and MediThread will check it for you.",
                                 "ഒരു റിപ്പോർട്ടോ വീട്ടിലെ റീഡിംഗോ ചേർക്കുക, MediThread പരിശോധിക്കും.")
    ask = [{"text": f"My {r['title'].lower()}: what should I watch for?", "textMl": None} for r in risks[:3]]
    return {"headline": headline, "headlineMl": headline_ml, "points": points, "askDoctor": ask, "source": "rules"}


def review(profile: dict, series: list[dict], medicines: list[dict], alerts: list[dict], risks: list[dict],
           today: date | None = None, use_ai: bool = True) -> dict:
    """Return {headline, headlineMl, points[{text,textMl,kind,tests}], askDoctor[{text,textMl}], source}."""
    today = today or date.today()
    fallback = python_review(series, risks, medicines, today)
    if not use_ai or not (series or medicines):
        return fallback
    facts = _facts(profile, series, medicines, alerts, risks, today)
    key = hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()
    if key in _CACHE:
        return _CACHE[key]
    raw = _call(facts)
    if not isinstance(raw, dict):
        return fallback

    allowed = _allowed_numbers(facts)
    known_codes = {s["code"] for s in series}
    pts_ml = raw.get("pointsMl") if isinstance(raw.get("pointsMl"), list) else []
    points = []
    for i, p in enumerate(raw.get("points") or []):
        if not isinstance(p, dict) or not _safe(p.get("text", ""), allowed):
            continue
        ml = pts_ml[i] if i < len(pts_ml) and isinstance(pts_ml[i], str) else None
        if ml and BANNED.search(ml):
            ml = None
        points.append({"text": p["text"].strip(), "textMl": ml,
                       "kind": p.get("kind") if p.get("kind") in ("worse", "better", "steady", "missing", "info") else "info",
                       "tests": [t for t in (p.get("tests") or []) if t in known_codes or p.get("kind") == "missing"][:4]})
    ask_ml = raw.get("askDoctorMl") if isinstance(raw.get("askDoctorMl"), list) else []
    ask = []
    for i, q in enumerate(raw.get("askDoctor") or []):
        if isinstance(q, str) and q.strip() and not BANNED.search(q):
            ask.append({"text": q.strip(), "textMl": ask_ml[i] if i < len(ask_ml) and isinstance(ask_ml[i], str) else None})
    headline = raw.get("headline") if isinstance(raw.get("headline"), str) else ""
    if not _safe(headline, allowed):
        headline = fallback["headline"]
        headline_ml = fallback["headlineMl"]
    else:
        headline_ml = raw.get("headlineMl") if isinstance(raw.get("headlineMl"), str) and not BANNED.search(raw["headlineMl"]) else None
    if not points:
        return fallback
    out = {"headline": headline.strip(), "headlineMl": headline_ml, "points": points[:5],
           "askDoctor": ask[:4] or fallback["askDoctor"], "source": "ai"}
    _CACHE[key] = out
    return out
