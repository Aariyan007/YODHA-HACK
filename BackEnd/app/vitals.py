"""Turns vitals into Observations: from the extractor's "vitals" dict and from spoken or typed text.

Plain regex, no AI. Used by the upload pipeline (Gemini returns {"bp": "150/95", ...}), by the doctor console on
approve (the doctor says "BP is 150 by 95") and by home readings.
"""
from __future__ import annotations

import re

from .labs import RULES

# Sensible limits. Anything outside is a misread and is dropped.
LIMITS = {"sbp": (50, 300), "dbp": (30, 200), "pulse": (20, 250), "spo2": (50, 100),
          "weight": (2, 300), "temp": (90, 110), "fbs": (20, 800), "ppbs": (20, 800), "rbs": (20, 800)}


def _num(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:\.\d+)?", str(v))
    return float(m.group(0)) if m else None


def _ok(code: str, v: float | None) -> bool:
    if v is None:
        return False
    lo, hi = LIMITS.get(code, (float("-inf"), float("inf")))
    return lo <= v <= hi


def obs(code: str, value: float) -> dict:
    r = RULES[code]
    return {"code": code, "name": r["name"], "value": value, "unit": r["unit"]}


def split_bp(text) -> tuple[float | None, float | None]:
    m = re.search(r"(\d{2,3})\s*(?:/|by|over)\s*(\d{2,3})", str(text or ""), re.I)
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


def from_extracted(vitals: dict | None) -> list[dict]:
    """Gemini's {"bp": "132/84", "pulse": 78, "weight_kg": 61, "spo2": 97, "temp_f": 99} becomes observations."""
    if not isinstance(vitals, dict):
        return []
    out: list[dict] = []
    s, d = split_bp(vitals.get("bp"))
    if _ok("sbp", s) and _ok("dbp", d) and s > d:
        out += [obs("sbp", s), obs("dbp", d)]
    for key, code in (("pulse", "pulse"), ("spo2", "spo2"), ("weight_kg", "weight"), ("weight", "weight"),
                      ("temp_f", "temp"), ("temperature", "temp")):
        v = _num(vitals.get(key))
        if code == "temp" and v is not None and v < 50:
            v = round(v * 9 / 5 + 32, 1)  # written in Celsius
        if _ok(code, v) and not any(o["code"] == code for o in out):
            out.append(obs(code, v))
    return out


# A number followed by a drug unit is a dose ("Glycomet 500 mg for sugar"), not a reading.
_NOT_DOSE = r"(?!\d|\.\d|\s*(?:mg|mcg|ml|units?|iu)\b)"

_TEXT_RULES = [
    ("bp", re.compile(r"\b(?:b\.?\s?p\.?|blood\s+pressure)\b[^0-9]{0,20}(\d{2,3})\s*(?:/|by|over)\s*(\d{2,3})" + _NOT_DOSE, re.I)),
    ("pulse", re.compile(r"\b(?:pulse|heart\s+rate|hr)\b[^0-9]{0,15}(\d{2,3})" + _NOT_DOSE, re.I)),
    ("spo2", re.compile(r"\b(?:spo2|sp\s?o2|oxygen(?:\s+saturation)?|saturation|sats?)\b[^0-9]{0,15}(\d{2,3})" + _NOT_DOSE, re.I)),
    ("fbs", re.compile(r"\bfasting\s+(?:blood\s+)?(?:sugar|glucose)\b[^0-9]{0,15}(\d{2,3})" + _NOT_DOSE, re.I)),
    ("ppbs", re.compile(r"\b(?:post[\s-]?(?:meal|prandial)|pp)\s+(?:blood\s+)?(?:sugar|glucose)\b[^0-9]{0,15}(\d{2,3})" + _NOT_DOSE, re.I)),
    ("rbs", re.compile(r"\b(?:random\s+)?(?:blood\s+)?(?:sugar|glucose|grbs|rbs)\b[^0-9]{0,15}(\d{2,3})" + _NOT_DOSE, re.I)),
    ("temp", re.compile(r"\b(?:temp(?:erature)?|fever)\b[^0-9]{0,15}(\d{2,3}(?:\.\d)?)" + _NOT_DOSE, re.I)),
    ("weight", re.compile(r"\bweigh(?:t|s|ing)?\b[^0-9]{0,15}(\d{2,3}(?:\.\d)?)\s*(?:kg|kilo)", re.I)),
]


def from_text(text: str) -> list[dict]:
    """Readings said in a visit, e.g. "BP is 150 by 95, pulse 88, sugar 260". The last mention of each wins."""
    found: dict[str, dict] = {}
    for code, rx in _TEXT_RULES:
        for m in rx.finditer(text or ""):
            if code == "bp":
                s, d = float(m.group(1)), float(m.group(2))
                if _ok("sbp", s) and _ok("dbp", d) and s > d:
                    found["sbp"], found["dbp"] = obs("sbp", s), obs("dbp", d)
                continue
            v = float(m.group(1))
            if code == "temp" and v < 50:
                v = round(v * 9 / 5 + 32, 1)
            # "fasting sugar 140" also matches the general sugar rule, keep the specific one.
            if code == "rbs" and ("fbs" in found or "ppbs" in found):
                continue
            if _ok(code, v):
                found[code] = obs(code, v)
    return list(found.values())
