"""When is this medicine usually taken, with or without food? From a public source, quoted word for word.

Source: the US FDA drug label database (openFDA, free, no key). We take the label's OWN sentence about food or time of day and
show it, with where it came from. Nothing is generated: the hint is read out of that sentence by fixed rules, so it can never say
something the label does not. This is general label information. It is never a replacement for the prescriber's instruction:
callers must only use it where the prescription says nothing, and must label it as general information.

Not found (Indian-only brands, unusual names) -> None, and the caller says so honestly."""
from __future__ import annotations

import re
import time

import httpx

URL = "https://api.fda.gov/drug/label.json"
FIELDS = ("dosage_and_administration", "directions", "information_for_patients", "patient_medication_information",
          "spl_patient_package_insert", "instructions_for_use")
SOURCE = "US FDA drug label (openFDA)"
TTL = 7 * 86400
_cache: dict[str, tuple[float, dict | None]] = {}

# (pattern, hint). Order matters: the more specific / stronger statements first.
RULES = [
    (r"\bwith or without (food|meals?)\b|\bregardless of (food|meals?)\b|\bwithout regard to (food|meals?)\b|\bindependent of (food|meals?)\b", "with or without food"),
    (r"\bon an empty stomach\b|\bat least (an |one |1 )?hour before\b[^.]{0,30}\b(meal|food|breakfast|eating)|\b(30|thirty) minutes before\b[^.]{0,30}\b(meal|food|breakfast|eating)|\bbefore (a |your |the )?(meals?|breakfast|eating|food)\b", "before food"),
    (r"\bafter (a |your |the )?(meals?|eating|food|breakfast)\b|\bfollowing (a |the )?meals?\b", "after food"),
    (r"\bwith (a |your |the )?(meals?|food|breakfast|dinner)\b|\bduring (a |the )?meals?\b", "with food"),
    (r"\bat bedtime\b|\bbefore bedtime\b|\bat night\b", "at bedtime"),
    (r"\bin the morning\b|\bevery morning\b|\bmorning\b", "in the morning"),
]


def clean_name(name: str) -> str:
    n = re.sub(r"\b\d[\d.,/]*\s*(mg|mcg|g|ml|iu|%)?\b", " ", name or "", flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z\- ]", " ", n)).strip()


def candidates(name: str) -> list[str]:
    from . import ddi, safety
    base = clean_name(name).lower()
    out: list[str] = []
    for c in (safety.to_generic(name), base, base.split(" ")[0] if base else ""):
        for v in (c, ddi.normalise(c) if c else None):
            if v and v not in out:
                out.append(v)
    return out


def _fetch(generic: str) -> list[dict]:
    r = httpx.get(URL, params={"search": f'openfda.generic_name:"{generic}"', "limit": 8}, timeout=8)
    labels = r.json().get("results", []) if r.status_code == 200 else []
    # Single-ingredient labels only: a combination product (e.g. metformin + sitagliptin) can say something different.
    only = [l for l in labels if all(g.lower().startswith(generic.lower()) and "," not in g and " and " not in g.lower()
                                     for g in (l.get("openfda") or {}).get("generic_name", [generic]))]
    return only


def pick(labels: list[dict]) -> dict | None:
    """The first sentence in the labels that says something about food or time of day, and the hint it gives."""
    for field in FIELDS:  # the dosage section first, then patient text
        best = None
        for lab in labels:
            text = re.sub(r"\s+", " ", " ".join(lab.get(field) or []))
            for sent in re.split(r"(?<=[.!?])\s+", text):
                s = re.sub(r"^\s*(\d+(\.\d+)*\s+)?(DOSAGE AND ADMINISTRATION|Important [A-Za-z ]+Information|Recommended Dosage)\s*", "", sent).strip()
                if not 15 <= len(s) <= 300 or "*" in s:  # table fragments are not sentences
                    continue
                for rx, hint in RULES:
                    if re.search(rx, s, re.I):
                        # Plain "take it with ..." sentences beat ones about particular doses; then the shortest reads cleanest.
                        rank = (bool(re.search(r"\d+\s*(mg|mcg|g)\b|\bdoses? (above|of|up to)\b", s, re.I)), len(s))
                        if best is None or rank < best["_rank"]:
                            best = {"hint": hint, "quote": s, "field": field, "_rank": rank}
                        break
        if best:
            best.pop("_rank")
            return best
    return None


def usage(name: str) -> dict | None:
    """{generic, hint, quote, source} or None. Cached for a week, 8 second budget per lookup, never raises."""
    key = clean_name(name).lower()
    if not key:
        return None
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    found = None
    try:
        for g in candidates(name)[:3]:
            labels = _fetch(g)
            if labels and (p := pick(labels)):
                found = {"generic": g, **p, "source": SOURCE}
                break
    except Exception:
        return None  # a network blip is not cached as "not found"
    _cache[key] = (time.time(), found)
    return found


# ---------------------------------------------------------------- side effects (from the same public label)

PATIENT_FIELDS = ("information_for_patients", "patient_medication_information", "spl_patient_package_insert")
_side_cache: dict[str, tuple[float, dict | None]] = {}
EXTRACT_SYSTEM = """You read the SOURCE text of a drug label and pull out side effects for a patient. Use ONLY the SOURCE.
List up to 8 side effects a patient may notice (common) and up to 4 serious ones where the SOURCE says to get medical help or call a doctor.
For every item copy a SHORT exact quote (under 110 characters) from the SOURCE that mentions it. Never add anything that is not in the SOURCE.
Reply JSON only: {"common": [{"effect": "plain name", "quote": "exact words"}], "serious": [{"effect": "plain name", "quote": "exact words"}]}"""


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", re.sub(r"\s+", " ", (t or "").lower())).strip()


def _source_text(labels: list[dict]) -> str:
    """The label's patient side-effects section if it has one, else the start of the adverse reactions section."""
    for field in PATIENT_FIELDS:
        for lab in labels:
            text = re.sub(r"\s+", " ", " ".join(lab.get(field) or []))
            m = re.search(r"(what are the possible side effects|possible side effects|side effects of)", text, re.I)
            if m:
                return text[m.start(): m.start() + 2600]
    for lab in labels:
        text = re.sub(r"\s+", " ", " ".join(lab.get("adverse_reactions") or []))
        if text:
            return text[:2600]
    return ""


def verify_items(items, source: str) -> list[dict]:
    """Keep an item only if its quote really is in the source and the effect is named in that quote. The model proposes, this decides."""
    src = _norm(source)
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        q, e = str(it.get("quote") or "").strip(), str(it.get("effect") or "").strip()
        words = [w for w in _norm(e).split() if len(w) > 3]
        if 8 <= len(q) <= 160 and _norm(q) in src and (not words or any(w[:4] in _norm(q) for w in words)):
            out.append({"effect": e[:60], "quote": q})
    return out[:8]


def side_effects(name: str, extractor=None) -> dict | None:
    """{generic, common[{effect,quote}], serious[...], boxed, source, summarised} or None. Cached, never raises.
    `extractor(system, user) -> dict|None` is the small model; without it only the label's boxed warning is returned."""
    key = clean_name(name).lower()
    if not key:
        return None
    hit = _side_cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    found = None
    try:
        for g in candidates(name)[:3]:
            labels = _fetch(g)
            if not labels:
                continue
            boxed = next((re.sub(r"\s+", " ", " ".join(l["boxed_warning"]))[:300] for l in labels if l.get("boxed_warning")), None)
            src = _source_text(labels)
            common = serious = []
            summarised = False
            if src and extractor is not None:
                out = extractor(EXTRACT_SYSTEM, "SOURCE:\n" + src)
                if isinstance(out, dict):
                    common, serious = verify_items(out.get("common"), src), verify_items(out.get("serious"), src)
                    summarised = True
            if common or serious or boxed or src:
                found = {"generic": g, "common": common, "serious": serious, "boxed": boxed, "source": SOURCE, "summarised": summarised,
                         "hasText": bool(src)}
                break
    except Exception:
        return None
    if found and (found["summarised"] or not found["hasText"]):  # do not cache a result that only lacked the model
        _side_cache[key] = (time.time(), found)
    return found
