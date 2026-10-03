"""Fixes medicine names that speech-to-text heard wrong in a transcript line.

Speech engines are weakest on drug names ("Glycomet" becomes "glycum"). A wrong drug name in a medical record
is a safety problem, so this is careful on purpose:

- It only touches sentences that sound like prescribing (a dose, "tablet", "start", "twice daily"...).
- It only replaces a word that isn't already a known medicine and isn't an ordinary English word.
- Tier 1 (the patient's own medicines + Indian brands and generics) allows a looser match, but the first three
  letters must agree. Tier 2 (DDInter generics) needs a close spelling match.
- Every change comes back as {"from", "to"} so the screen can show it and the doctor can undo it.
  Nothing is changed silently.
"""
from __future__ import annotations

import difflib
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

from .safety import BRAND_TO_GENERIC

_DDI_DB = Path(__file__).resolve().parents[1] / "data" / "ddi" / "ddi.sqlite"

# Words used in prescribing talk that must never get 'corrected' into a drug.
_ORDINARY = {
    "daily", "twice", "thrice", "before", "after", "morning", "evening", "night", "dosage", "tablet", "tablets",
    "capsule", "capsules", "syrup", "injection", "weeks", "months", "medicine", "medicines", "medication",
    "prescribe", "prescribed", "continue", "continued", "start", "started", "stopped", "taking", "takes",
    "breakfast", "lunch", "dinner", "bedtime", "though", "should", "would", "could", "every", "other",
    "sugar", "blood", "pressure", "doctor", "patient", "report", "result", "results", "normal", "check",
}

# A sentence that sounds like it is about a medicine.
_CONTEXT = re.compile(
    r"\b(tab(let)?s?|cap(sule)?s?|syrup|inj(ection)?|mg|mcg|ml|dose|dosage|start|stop|continue|prescrib\w*|"
    r"take|taking|medicine|medication|twice|thrice|daily|bd|od|tds|hs|sos|prn|before\s+food|after\s+food)\b|\d+\s*mg",
    re.I,
)
_WORD = re.compile(r"[A-Za-z][A-Za-z\-]{4,}")


@lru_cache(maxsize=1)
def _tiers() -> tuple[frozenset[str], frozenset[str]]:
    """(tier1, tier2), built once. Tier 1 = Indian brands and their generics, tier 2 = DDInter generics."""
    t1 = {w.lower() for w in list(BRAND_TO_GENERIC) + list(BRAND_TO_GENERIC.values())}
    t1 = {w for w in t1 if len(w) >= 5 and re.fullmatch(r"[a-z\-]+", w)}
    t2: set[str] = set()
    try:
        con = sqlite3.connect(f"file:{_DDI_DB}?mode=ro", uri=True)
        for (name,) in con.execute("select name from drugs"):
            n = (name or "").lower().strip()
            if len(n) >= 5 and re.fullmatch(r"[a-z\-]+", n):
                t2.add(n)
        con.close()
    except Exception as e:  # dataset missing: tier 1 still works
        print(f"[medterms] DDInter list unavailable: {type(e).__name__}")
    return frozenset(t1), frozenset(t2 - t1)


def common_brands(limit: int = 16) -> list[str]:
    """Indian brand names (not generics) to prime Whisper with."""
    out = [b.capitalize() for b, g in BRAND_TO_GENERIC.items() if b != g and len(b) >= 4]
    return out[:limit]


def _match(word: str, pool, cutoff: float, need_prefix: bool) -> str | None:
    cands = difflib.get_close_matches(word, pool, n=3, cutoff=cutoff)
    for c in cands:
        if not need_prefix or c[:3] == word[:3]:
            return c
    return None


def correct(text: str, patient_meds: list[str] | None = None) -> tuple[str, list[dict]]:
    """Returns (text, fixes). fixes = [{"from": heard, "to": medicine}]. Text is unchanged when unsure."""
    if not text or not _CONTEXT.search(text):
        return text, []
    t1, t2 = _tiers()
    mine = {m.lower() for m in (patient_meds or []) if m and len(m) >= 4 and " " not in m.strip()}
    known = t1 | t2 | mine
    tier1 = t1 | mine
    fixes: list[dict] = []

    def fix(m: re.Match) -> str:
        w = m.group(0)
        lw = w.lower()
        if lw in known or lw in _ORDINARY:
            return w
        to = _match(lw, mine, 0.68, True) or _match(lw, tier1, 0.68, True) or _match(lw, t2, 0.82, True)
        if not to or to == lw:
            return w
        is_brand = BRAND_TO_GENERIC.get(to) not in (None, to)
        out = to.capitalize() if (w[0].isupper() or is_brand) else to
        fixes.append({"from": w, "to": out})
        return out

    return _WORD.sub(fix, text), fixes
