"""Sorts a finished visit transcript into the parts a clinician cares about.

Output is always this shape, or None if the AI call fails:
    {
      "complaints": [{"text", "source_lines"}],      what the patient reported
      "diagnoses":  [{"text", "source_lines"}],      only conditions the doctor said out loud
      "medicines":  [{"name", "generic", "action", "dose", "frequency", "timing", "duration",
                      "instructions", "source_lines"}],    start / continue / change / stop
      "tests":      [{"text", "source_lines"}],      tests or scans the doctor ordered
      "advice":     [{"text", "source_lines"}],      diet, rest, lifestyle
      "referrals":  [{"text", "source_lines"}],
      "follow_up":  {"text", "source_lines"} | None,
      "ignored_lines": [int],                        small talk, never used anywhere
      "source": "ai"
    }

The model proposes and code decides what stays ("grounding"):
- every item needs valid transcript line numbers
- diagnoses, medicines, tests, advice, referrals and follow-up must cite at least one DOCTOR line
- an item must share real words with the lines it cites, so it can't be invented
- dose, frequency, timing and duration become None unless the cited words really have that cue
Missing detail stays missing. This never diagnoses and never adds a medicine nobody prescribed.
"""
from __future__ import annotations

import re
from typing import Any

from .consultation import FALLBACK_MODEL, _chat_json, _lines_block
from .safety import to_generic

_SYSTEM = (
    "You are a careful clinical scribe. Read a doctor-patient visit transcript. Each line starts with its index, "
    "like '[3] doctor: ...'. Sort what was said into categories and reply as ONE JSON object.\n"
    "IGNORE small talk completely: greetings, jokes, weather, traffic, family chat, scheduling chat, thanks, anything "
    "not about the patient's health. List the index of every ignored line in 'ignored_lines'. "
    "Anything about health is NOT small talk, even if it is not prescribed (for example a supplement the patient "
    "mentions): never put such a line in ignored_lines.\n"
    "Keys:\n"
    "- complaints: [{text, source_lines}] symptoms or problems the PATIENT reports.\n"
    "- diagnoses: [{text, source_lines}] ONLY a condition or impression the DOCTOR explicitly states. "
    "Never infer one. If the doctor named none, use [].\n"
    "- medicines: [{name, action, dose, frequency, timing, duration, instructions, source_lines}] medicines the "
    "DOCTOR starts, continues, changes or stops. action is one of start, continue, change, stop. "
    "Do NOT list medicines only the patient mentions, and do not list allergies. "
    "dose like '500 mg'; frequency like 'twice daily' or 'BD'; timing like 'after breakfast' or 'at night'; "
    "duration like '7 days'. Use null for anything the doctor did not say. Never guess a missing detail.\n"
    "- tests: [{text, source_lines}] blood tests, scans or other investigations the doctor orders.\n"
    "- advice: [{text, source_lines}] diet, rest, exercise, lifestyle or warning-sign advice from the doctor.\n"
    "- referrals: [{text, source_lines}] if the doctor sends the patient to another specialist.\n"
    "- follow_up: {text, source_lines} or null: when the doctor wants to see the patient again.\n"
    "- ignored_lines: [int].\n"
    "source_lines are the transcript indexes that support the item. Write item text in English. Keep medicine "
    "names exactly as spoken. The transcript may mix English and Malayalam. Return no extra keys."
)

# A cue has to really be in the cited words before we keep a medicine detail.
_FREQ = re.compile(r"\b(od|bd|bid|tds|tid|qid|qds|hs|sos|prn|once|twice|thrice|daily|nightly|times?|every|weekly|"
                   r"morning|evening|night|bedtime|\d\s*-\s*\d\s*-\s*\d)\b", re.I)
_TIMING = re.compile(r"\b(food|meal|meals|breakfast|lunch|dinner|bedtime|night|morning|evening|empty\s+stomach|"
                     r"before|after|with\s+water|hs)\b", re.I)
_DURATION = re.compile(r"(\d+\s*(d|day|days|w|wk|week|weeks|month|months)\b|\bfor\s+a\s+(week|month|fortnight)\b|"
                       r"fortnight|\bx\s*\d+)", re.I)
_DOSE = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|iu|units?)\b", re.I)
_ACTIONS = {"start", "continue", "change", "stop"}
_MAX_TEXT = 400


def _stems(text: str) -> set[str]:
    return {t[:5] for t in re.findall(r"[a-z0-9]{4,}", (text or "").lower())}


def _lines_ok(raw: Any, lines: list[dict]) -> list[int]:
    if not isinstance(raw, list):
        return []
    out = []
    for x in raw:
        if isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= int(x) < len(lines) and int(x) not in out:
            out.append(int(x))
    return out


def _cited(src: list[int], lines: list[dict]) -> tuple[str, bool]:
    text = " ".join(lines[i].get("text", "") for i in src)
    by_doctor = any(lines[i].get("speaker") == "doctor" for i in src)
    return text, by_doctor


def _text_item(obj: Any, lines: list[dict], need_doctor: bool) -> dict | None:
    if not isinstance(obj, dict) or not isinstance(obj.get("text"), str) or not obj["text"].strip():
        return None
    src = _lines_ok(obj.get("source_lines"), lines)
    if not src:
        return None
    cited, by_doctor = _cited(src, lines)
    if need_doctor and not by_doctor:
        return None
    text = obj["text"].strip()[:_MAX_TEXT]
    if not (_stems(text) & _stems(cited)):  # shares no real word with what it cites: invented
        return None
    return {"text": text, "source_lines": src}


def _detail(value: Any, cue: re.Pattern, cited: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:80] if cue.search(cited) else None


_SENTENCE_END = re.compile(r"[.!?;\n]+")


def _own_words(name: str, src: list[int], lines: list[dict], all_names: list[str]) -> str:
    """The words that belong to ONE medicine: from its name to the next medicine's name (or the end of the sentence).
    
    One line often has several medicines ("Continue Telma 40 mg in the morning. Stop ibuprofen."). Checking cues on the
    whole line would let one medicine's "morning" justify another medicine's made-up timing.
    """
    others = [n.lower() for n in all_names if n.lower() != name.lower()]
    parts = []
    for i in src:
        if lines[i].get("speaker") != "doctor":
            continue
        for sentence in _SENTENCE_END.split(lines[i].get("text", "")):
            low = sentence.lower()
            pos = low.find(name.lower())
            if pos < 0:
                continue
            end = len(sentence)
            for o in others:
                j = low.find(o, pos + len(name))
                if j >= 0:
                    end = min(end, j)
            parts.append(sentence[pos:end])
    return " ".join(parts)


def _medicine(obj: Any, lines: list[dict], all_names: list[str]) -> dict | None:
    if not isinstance(obj, dict) or not isinstance(obj.get("name"), str):
        return None
    name = obj["name"].strip()
    src = _lines_ok(obj.get("source_lines"), lines)
    if not name or len(name) > 60 or not src:
        return None
    cited = _own_words(name, src, lines, all_names)
    if not cited:  # the doctor must have actually said this name, in a line cited for it
        return None
    action = str(obj.get("action") or "start").lower()
    if action not in _ACTIONS:
        action = "start"
    dose = obj.get("dose")
    dose_ok = None
    if isinstance(dose, str):
        m = _DOSE.search(dose)
        if m and re.search(rf"{re.escape(m.group(1))}\s*{m.group(2)}", cited, re.I):
            dose_ok = f"{m.group(1)} {m.group(2).lower()}"
    instr = obj.get("instructions")
    instr_ok = None
    if isinstance(instr, str) and instr.strip() and (_stems(instr) & _stems(cited)):
        instr_ok = instr.strip()[:160]
    return {
        "name": name,
        "generic": to_generic(name),
        "action": action,
        "dose": dose_ok,
        "frequency": _detail(obj.get("frequency"), _FREQ, cited),
        "timing": _detail(obj.get("timing"), _TIMING, cited),
        "duration": _detail(obj.get("duration"), _DURATION, cited),
        "instructions": instr_ok,
        "source_lines": src,
    }


def validate(raw: Any, lines: list[dict]) -> dict | None:
    """Turns the model's JSON into the safe, grounded shape. None if it isn't even an object."""
    if not isinstance(raw, dict) or not lines:
        return None
    out: dict[str, Any] = {"source": "ai"}
    out["complaints"] = [i for i in (_text_item(x, lines, False) for x in (raw.get("complaints") or [])) if i][:12]
    for key in ("diagnoses", "tests", "advice", "referrals"):
        out[key] = [i for i in (_text_item(x, lines, True) for x in (raw.get(key) or [])) if i][:12]
    seen: set[str] = set()
    meds = []
    raw_meds = [x for x in (raw.get("medicines") or []) if isinstance(x, dict)]
    all_names = [x["name"].strip() for x in raw_meds if isinstance(x.get("name"), str) and x["name"].strip()]
    for m in (_medicine(x, lines, all_names) for x in raw_meds):
        if m and m["name"].lower() not in seen:
            seen.add(m["name"].lower())
            meds.append(m)
    out["medicines"] = meds[:20]
    out["follow_up"] = _text_item(raw.get("follow_up"), lines, True)
    out["ignored_lines"] = _lines_ok(raw.get("ignored_lines"), lines)
    return out


def classify(lines: list[dict], active_medicines: list[str] | None = None) -> dict | None:
    """Classifies a visit. Returns None if the AI is unavailable, so callers use the old extraction."""
    if not lines:
        return None
    context = ""
    if active_medicines:
        context = f"\n(For context only, the patient's current medicines: {', '.join(active_medicines[:20])}.)"
    user = _lines_block(lines) + context
    # wait_on_limit: this runs once at the end of a visit, so waiting a few seconds for the free tier limit is fine.
    raw = _chat_json(_SYSTEM, user, max_tokens=2000, wait_on_limit=8.0, fallback_model=FALLBACK_MODEL)
    out = validate(raw, lines)
    if out is None:
        raw = _chat_json(_SYSTEM, user, max_tokens=2400, wait_on_limit=8.0, fallback_model=FALLBACK_MODEL)  # one retry on malformed output
        out = validate(raw, lines)
    return out
