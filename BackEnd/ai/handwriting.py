"""Handwritten prescriptions: clean up, read twice, flag what's unclear. Leave it empty rather than guess.

A model is most likely to invent a believable drug name from doctors' handwriting. So when the first pass says
handwritten:
1. the page is cleaned up (grey, contrast, upscaled, sharpened)
2. a second, separate reading goes line by line and writes [?] for any word it can't read
3. code compares the two. A medicine is "certain" only if both passes agree on the name and it's a known drug.
   Everything else goes to uncertain_medicines with what each pass saw, and is not treated as a medicine.
The person is told to check those with the doctor or pharmacist. Nothing is guessed quietly.
"""
from __future__ import annotations

import difflib
import io
import json
import re

HW_PROMPT = """This is a HANDWRITTEN medical note or prescription. Read it very carefully, line by line, exactly as written.
Return STRICTLY one JSON object:
{
  "lines": ["each line exactly as written; write [?] in place of any word or letters you cannot read"],
  "medicines": [{"name": "as written, or with [?] where unclear", "dose": "as written or null", "schedule": "as written or null", "confidence": "high" | "low"}]
}
Rules:
- NEVER guess. If a drug name is not clearly legible, keep the letters you can see and use [?] for the rest, and set confidence "low".
- Do not correct spelling to a drug you think it might be. Do not add anything that is not on the page.
- Output ONLY JSON."""


def preprocess(data: bytes, mime: str) -> bytes:
    """Grey, auto contrast, upscale small photos, sharpen. Returns PNG bytes, or the original if it isn't a plain image."""
    if not mime.startswith("image/"):
        return data
    try:
        from PIL import Image, ImageFilter, ImageOps
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
        im = ImageOps.autocontrast(im, cutoff=1)
        w, h = im.size
        if max(w, h) < 1800:
            k = 1800 / max(w, h)
            im = im.resize((int(w * k), int(h * k)), Image.LANCZOS)
        im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=140, threshold=3))
        out = io.BytesIO()
        im.save(out, "PNG")
        return out.getvalue()
    except Exception:
        return data


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9?]+", "", (s or "").lower())


def _known(name: str) -> bool:
    from . import ddi, safety
    first = (re.split(r"[\s\-/]+", name.strip().lower()) or [""])[0]
    return bool(first) and (safety.to_generic(name) is not None or ddi.known_drug(first) or ddi.known_drug(name))


DETAIL_KEYS = ("dose", "schedule", "times", "duration", "purpose")


def _details(m: dict) -> dict:
    """What the first reading saw next to the name, so confirming the name doesn't lose it."""
    return {k: m.get(k) for k in DETAIL_KEYS if m.get(k) not in (None, "", [])}


def compare(first: list[dict], second: list[dict]) -> tuple[list[dict], list[dict]]:
    """Gives (certain, uncertain). Certain only if both readings agree, the second is confident and readable, and the name is a real drug."""
    certain, uncertain = [], []
    pool = [dict(m) for m in second or []]
    for m in first or []:
        name = str(m.get("name") or "").strip()
        if not name:
            continue
        best, score = None, 0.0
        for cand in pool:
            r = difflib.SequenceMatcher(None, _norm(name), _norm(str(cand.get("name") or ""))).ratio()
            if r > score:
                best, score = cand, r
        why = None
        if best is None or score < 0.8:
            why = "the two readings of the page do not agree on this name"
        elif "?" in str(best.get("name")) or "?" in name:
            why = "part of the name is not legible"
        elif str(best.get("confidence", "low")).lower() != "high":
            why = "the second reading was not sure"
        elif not _known(name):
            why = "this does not match a drug name I know"
        if why:
            uncertain.append({"name": name, "alternative": (best or {}).get("name"), "reason": why, "details": _details(m)})
        else:
            certain.append(m)
    return certain, uncertain


def second_pass(client, call, data: bytes, mime: str, doc: dict) -> dict:
    """Runs the second reading and rewrites the doc's medicines and lines. `call` is extractor._call (retries and model fallback)."""
    img = preprocess(data, mime)
    out_mime = "image/png" if img is not data and mime.startswith("image/") else mime
    try:
        raw = call(client, img, out_mime, HW_PROMPT)
        second = json.loads(re.sub(r"^```[a-zA-Z]*\n|\n```$", "", raw.strip()))
    except Exception:
        second = None
    meds = doc.get("medicines") or []
    if second is None:  # could not double-check: nothing handwritten is trusted as a medicine
        doc["uncertain_medicines"] = [{"name": str(m.get("name")), "alternative": None, "reason": "I could not double-check this handwriting", "details": _details(m)} for m in meds]
        doc["medicines"] = []
    else:
        certain, uncertain = compare(meds, second.get("medicines") or [])
        doc["medicines"], doc["uncertain_medicines"] = certain, uncertain
        lines = [str(l) for l in (second.get("lines") or []) if str(l).strip()]
        if len(lines) >= len(doc.get("source_lines") or []):
            doc["source_lines"] = lines  # the careful reading keeps [?] where the page is unclear
    doc["handwritten"] = True
    _third_reader(img, doc)
    return doc


def _third_reader(img: bytes, doc: dict) -> None:
    """Optional TrOCR reader (htr/ service). It only adds info: which accepted medicines it also saw, and an extra
    warning on names it couldn't find when the page text it read was long. It never makes a medicine certain.
    """
    from . import htr
    lines = htr.read(img)
    if not lines:
        return
    doc["htr_lines"] = lines[:40]
    substantial = sum(len(l) for l in lines) >= 20
    keep, demote = [], []
    for m in doc.get("medicines") or []:
        saw = htr.seen(str(m.get("name") or ""), lines)
        m["htr_seen"] = saw
        if substantial and not saw and not m.get("dose"):  # no dose written and the third reader never saw the name: too thin to trust
            demote.append({"name": str(m.get("name")), "alternative": None, "reason": "a third reader did not find this name on the page", "details": _details(m)})
        else:
            keep.append(m)
    doc["medicines"] = keep
    doc["uncertain_medicines"] = (doc.get("uncertain_medicines") or []) + demote
