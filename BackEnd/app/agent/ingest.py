"""File helpers: the PDF text layer and document classification.

Classification never guesses. Keyword scores give a type with a confidence, and below the line the type is None
and the agent has to ask the person. The file's text is data: it's only counted and quoted, never read as instructions.
"""
from __future__ import annotations

import io
import re

MAX_PAGES = 30
MAX_CHARS = 60_000

KEYWORDS = {
    "lab": ["hba1c", "haemoglobin", "hemoglobin", "creatinine", "cholesterol", "reference range", "bio. ref", "specimen",
            "pathology", "laboratory", "sample collected", "result", "units", "mg/dl", "g/dl", "ldl", "triglyceride", "tsh", "platelet"],
    "prescription": ["rx", "tab ", "tab.", "cap ", "cap.", "syp", "inj ", "bd", "tds", "od ", "1-0-1", "0-0-1", "after food", "before food",
                     "prescription", "dispense", "sig:", "mg "],
    "visit": ["discharge summary", "consultation", "history of present", "chief complaint", "diagnosis", "advice", "follow up",
              "follow-up", "examination", "clinical notes", "assessment", "plan:", "impression"],
    "scan": ["x-ray", "xray", "ultrasound", "usg", "ct scan", "mri", "radiolog", "findings:", "impression:", "echocardiogram", "ecg"],
}
LABELS = {"lab": "lab report", "prescription": "prescription", "visit": "visit or discharge note", "scan": "scan report"}


def pdf_pages(data: bytes) -> tuple[list[str], int]:
    """Text per page (empty for scanned pages) and the page count. Never raises."""
    try:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(data))
        if r.is_encrypted:
            return [], 0
        out, total = [], 0
        for i, page in enumerate(r.pages):
            total += 1
            if i >= MAX_PAGES:
                continue
            try:
                out.append((page.extract_text() or "").strip())
            except Exception:
                out.append("")
        return out, total
    except Exception:
        return [], 0


def text_lines(pages: list[str]) -> list[dict]:
    """Numbered lines with their page, the unit we use as evidence."""
    lines, used = [], 0
    for pno, text in enumerate(pages, 1):
        for raw in text.splitlines():
            line = re.sub(r"\s+", " ", raw).strip()
            if not line:
                continue
            used += len(line)
            if used > MAX_CHARS:
                return lines
            lines.append({"n": len(lines) + 1, "page": pno, "text": line})
    return lines


def classify(text: str) -> dict:
    low = " " + text.lower() + " "
    if len(low.strip()) < 40:
        return {"type": None, "confidence": 0.0, "source": "none", "reason": "no readable text layer"}
    scores = {t: sum(low.count(k) for k in ks) for t, ks in KEYWORDS.items()}
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    (best, s1), (_, s2) = ranked[0], ranked[1]
    if s1 >= 4 and s1 - s2 >= 2:
        conf = 0.85
    elif s1 >= 2 and s1 > s2:
        conf = 0.6
    else:
        conf = 0.3
    return {"type": best if conf >= 0.6 else None, "confidence": conf, "source": "text", "scores": scores,
            "reason": None if conf >= 0.6 else "the words do not clearly say what kind of document this is"}
