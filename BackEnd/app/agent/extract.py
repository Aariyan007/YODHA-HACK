"""Structured extraction with provenance. Null over fabrication.

The model (Gemini) reads the document and proposes fields. CODE then decides what survives: every value must be found in
the document's own text lines, and each kept value carries the line numbers (and page) it came from. Anything that cannot be
found is listed as unverified and is NOT part of `clean_doc`, which is the only thing a later confirmed write may use.

Document text is untrusted data. It is searched and quoted; it is never executed or followed. Text that looks like an
instruction to an AI is reported as a warning and otherwise ignored.
"""
from __future__ import annotations

import re
from typing import Callable

from . import ingest

INJECTION = re.compile(r"ignore (all |any |the )?(previous|prior|above)|disregard .{0,30}instruction|system prompt|you are (now )?an? (ai|assistant)|"
                       r"as an ai|call the .{0,20}tool|reveal .{0,20}(key|prompt|token)|share (this|the) (record|file) with", re.I)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w./%-]+", " ", str(s or "").lower())).strip()


def _has_num(text: str, value) -> bool:
    cands = {f"{value:g}"} if isinstance(value, (int, float)) else set()
    cands.add(str(value))
    return any(re.search(rf"(?<![\d.]){re.escape(c)}(?![\d])", text) for c in cands if c)


def _ev(line: dict) -> dict:
    return {"lines": [line["n"]], "page": line["page"], "quote": line["text"][:160]}


def _find(lines: list[dict], pred: Callable[[str], bool], span: int = 1) -> dict | None:
    """The line where pred(normalised text) holds. Single lines first (so the evidence is the line that really says it);
    only then a line joined with the next one(s), because table cells sometimes wrap."""
    for l in lines:
        if pred(_norm(l["text"])):
            return l
    if span:
        for i, l in enumerate(lines):
            if pred(" ".join(_norm(x["text"]) for x in lines[i:i + 1 + span])):
                return l
    return None


def lines_for(file_bytes_pages: list[str], gemini_lines: list[str]) -> list[dict]:
    """The text layer if the PDF has one (page-accurate), else the lines the vision model read."""
    if any(file_bytes_pages):
        return ingest.text_lines(file_bytes_pages)
    return [{"n": i + 1, "page": 1, "text": str(t)[:300]} for i, t in enumerate(gemini_lines[:400]) if str(t).strip()]


def verify(doc: dict, lines: list[dict]) -> dict:
    """Return {clean_doc, items, unverified, warnings}. `items` is what the UI shows (with evidence)."""
    warnings: list[str] = []
    if any(INJECTION.search(l["text"]) for l in lines):
        warnings.append("This document contains text that reads like instructions to an AI. I ignored it and treated it as plain text.")
    items: dict[str, list[dict]] = {"diagnoses": [], "medicines": [], "observations": [], "vitals": []}
    unverified: list[dict] = []
    clean = {k: doc.get(k) for k in ("date_of_record", "doctor", "hospital", "type", "follow_up")}
    clean.update({"diagnoses": [], "medicines": [], "observations": [], "vitals": {}, "source_lines": [l["text"] for l in lines]})

    for d in doc.get("diagnoses") or []:
        words = [w for w in _norm(d).split() if len(w) > 3]
        hit = _find(lines, lambda t: bool(words) and sum(w in t for w in words) >= max(1, (len(words) + 1) // 2))
        if hit:
            items["diagnoses"].append({"text": str(d)[:200], "evidence": _ev(hit)})
            clean["diagnoses"].append(str(d)[:200])
        else:
            unverified.append({"kind": "diagnosis", "text": str(d)[:200]})

    for m in doc.get("medicines") or []:
        name = str(m.get("name") or "")
        first = (_norm(name).split() or [""])[0]
        hit = _find(lines, lambda t: len(first) >= 3 and first in t)
        if not hit:
            unverified.append({"kind": "medicine", "text": name[:120]})
            continue
        m = dict(m)
        dose = str(m.get("dose") or "")
        nd = _norm(dose).replace(" ", "")
        if dose and nd:
            ok = _find(lines, lambda t: first in t and nd in t.replace(" ", ""), span=1)
            if not ok:
                m["dose"] = None  # the written dose could not be found next to the name: leave it blank rather than guess
        items["medicines"].append({"name": name[:120], "dose": m.get("dose"), "schedule": m.get("schedule"), "purpose": m.get("purpose"),
                                   "doseVerified": bool(m.get("dose")), "evidence": _ev(hit)})
        clean["medicines"].append(m)

    for o in doc.get("observations") or []:
        name = str(o.get("name") or "")
        first = (_norm(name).split() or [""])[0]
        val = o.get("value")
        try:
            val = float(val)
        except (TypeError, ValueError):
            unverified.append({"kind": "result", "text": name[:120]})
            continue
        hit = _find(lines, lambda t: len(first) >= 2 and first in t and _has_num(t, val), span=1)
        if not hit:
            unverified.append({"kind": "result", "text": f"{name[:80]} {val:g}"})
            continue
        o = dict(o)
        o["value"] = val
        items["observations"].append({"name": name[:120], "value": val, "unit": o.get("unit"), "range": o.get("range"),
                                      "evidence": _ev(hit)})
        clean["observations"].append(o)

    for u in doc.get("uncertain_medicines") or []:  # handwriting the two readings could not agree on: listed, never written
        alt = f" (the other reading saw: {u['alternative']})" if u.get("alternative") else ""
        unverified.append({"kind": "medicine", "text": f"{str(u.get('name'))[:80]}{alt}: {u.get('reason')}. Please check with the doctor or pharmacist."})
    if doc.get("handwritten"):
        warnings.append("This looks handwritten. I read it twice; anything the readings did not agree on is listed as unclear instead of being guessed.")

    v = doc.get("vitals") or {}
    for key, label in (("bp", "BP"), ("pulse", "Pulse"), ("spo2", "SpO2"), ("weight_kg", "Weight"), ("temp_f", "Temperature")):
        if v.get(key) in (None, ""):
            continue
        val = v[key]
        hit = _find(lines, lambda t: (str(val).replace(" ", "") in t.replace(" ", "")) if key == "bp" else _has_num(t, val), span=0)
        if hit:
            items["vitals"].append({"name": label, "value": val, "evidence": _ev(hit)})
            clean["vitals"][key] = val
        else:
            unverified.append({"kind": "vital", "text": f"{label} {val}"})

    return {"clean_doc": clean, "items": items, "unverified": unverified, "warnings": warnings}


def classification_check(gemini_type: str | None, text_cls: dict | None, found_any: bool) -> dict:
    """Combine the model's type with the keyword check. Disagreement or an empty result means ask the person."""
    if text_cls and text_cls.get("type") and gemini_type and text_cls["type"] != gemini_type:
        return {"type": None, "confidence": 0.3, "source": "disagree", "reason": "I read this one way and the words suggest another"}
    if not found_any:
        return {"type": None, "confidence": 0.2, "source": "model", "reason": "I could not find any medicines, results or diagnoses I can point to"}
    conf = 0.9 if (text_cls and text_cls.get("type") == gemini_type) else 0.7
    return {"type": gemini_type, "confidence": conf, "source": "model+text" if conf == 0.9 else "model"}
