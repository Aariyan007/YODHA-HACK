"""PDF generation from structured records. Every fact carries a numbered source (document title + date); the footer states
what the file is and is not. No internal ids, paths or tokens go in the text or in the PDF metadata.

reportlab's built-in fonts do not cover Malayalam (it also does not shape complex scripts), so PDFs are English; characters
outside Latin-1 are replaced with '?' rather than rendered wrongly."""
from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

DISCLAIMER = ("Prepared by MediThread from the patient's own records. It is a summary, not medical advice, and it may be incomplete. "
              "Please check it with a doctor.")
SAGE, INK = colors.HexColor("#4E7A70"), colors.HexColor("#223029")


def _t(x) -> str:
    s = "" if x is None else str(x)
    return escape(s.encode("latin-1", "replace").decode("latin-1"))


class Sources:
    """Collects the documents a fact came from and hands out [n] markers."""
    def __init__(self):
        self.items: list[tuple[str, str]] = []

    def ref(self, title: str | None, d: str | None) -> str:
        if not title and not d:
            return ""
        key = (title or "Record", d or "")
        if key not in self.items:
            self.items.append(key)
        return f" [{self.items.index(key) + 1}]"


def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=20, textColor=INK, alignment=0, spaceAfter=4),
        "sub": ParagraphStyle("sub", parent=ss["Normal"], fontSize=9.5, textColor=colors.HexColor("#5B6B63"), spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, textColor=SAGE, spaceBefore=12, spaceAfter=4),
        "p": ParagraphStyle("p", parent=ss["Normal"], fontSize=10, leading=14, textColor=INK),
        "small": ParagraphStyle("small", parent=ss["Normal"], fontSize=8.5, leading=11, textColor=colors.HexColor("#5B6B63")),
    }


def _table(rows: list[list[str]], widths) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9), ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                           ("TEXTCOLOR", (0, 0), (-1, 0), SAGE), ("LINEBELOW", (0, 0), (-1, 0), 0.6, SAGE),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#D5DDD6")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    return t


def build(kind: str, data: dict) -> tuple[bytes, int]:
    """`data` is plain structured records (see tools/pdf.py). Returns (pdf bytes, page count)."""
    st = _styles()
    src = Sources()
    story: list = []
    p = data["patient"]
    title = {"patient_summary": "Health summary", "medication_summary": "Medication summary", "visit_prep": "Visit preparation"}[kind]
    story += [Paragraph(_t(title), st["h1"]),
              Paragraph(_t(f"{p['name']}" + (f", {p['age']} years" if p.get("age") else "") + (f", {p['gender']}" if p.get("gender") else "")
                           + (f" | Blood group {p['bloodGroup']}" if p.get("bloodGroup") else "") + f" | Prepared {date.today().isoformat()}"), st["sub"])]

    def section(name: str, rows=None, lines=None, empty="Nothing recorded."):
        story.append(Paragraph(_t(name), st["h2"]))
        if rows:
            story.append(rows)
        elif lines:
            story.extend(Paragraph(_t(l), st["p"]) for l in lines)
        else:
            story.append(Paragraph(_t(empty), st["small"]))

    if kind in ("patient_summary", "visit_prep"):
        section("Conditions and allergies", lines=[l for l in (
            ("Conditions: " + ", ".join(map(str, p["conditions"]))) if p.get("conditions") else None,
            ("Allergies: " + ", ".join(map(str, p["allergies"]))) if p.get("allergies") else None) if l])
    if kind in ("patient_summary", "medication_summary", "visit_prep"):
        meds = data["medicines"]
        rows = [["Medicine", "Dose", "When", "Prescribed by"]] + [
            [_t(m["name"]) + _t(src.ref(m.get("sourceTitle"), m.get("sourceDate"))), _t(m.get("dose") or "-"),
             _t(" ".join(x for x in (m.get("frequency"), ", ".join(m.get("times") or [])) if x) or "-"), _t(m.get("prescribedBy") or "-")]
            for m in meds]
        section("Current medicines", rows=_table([[Paragraph(c, st["p"]) for c in r] if i else r for i, r in enumerate(rows)],
                                                 [60 * mm, 28 * mm, 50 * mm, 40 * mm]) if meds else None, empty="No current medicines are recorded.")
    if kind in ("patient_summary", "visit_prep"):
        labs = data["labs"]
        rows = [["Test", "Latest", "Date", "Status"]] + [
            [_t(l["name"]) + _t(src.ref(l.get("sourceTitle"), l.get("sourceDate"))), _t(f"{l['value']:g} {l.get('unit') or ''}".strip()), _t(l["date"]), _t(l["status"])]
            for l in labs]
        section("Latest results", rows=_table([[Paragraph(c, st["p"]) for c in r] if i else r for i, r in enumerate(rows)],
                                              [60 * mm, 40 * mm, 30 * mm, 30 * mm]) if labs else None, empty="No results are recorded.")
        section("Needs attention", lines=[f"{a['title']}: {a['message']}" for a in data["alerts"][:8]], empty="No open warnings.")
    if kind == "patient_summary":
        section("Recent records", lines=[f"{d['date']}  {d['title']} ({d['type']})" + _t(src.ref(d["title"], d["date"])).replace("&amp;", "&") for d in data["records"][:8]])
    if kind in ("visit_prep", "patient_summary") and data.get("questions"):
        section("Questions to ask the doctor", lines=[f"{i}. {q}" for i, q in enumerate(data["questions"][:6], 1)])
    if src.items:
        section("Sources", lines=[f"[{i}] {t}" + (f", {d}" if d else "") for i, (t, d) in enumerate(src.items, 1)])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#5B6B63"))
        canvas.drawString(18 * mm, 12 * mm, DISCLAIMER[:150])
        canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=20 * mm,
                            title=title, author="MediThread", subject="Summary from the patient's own records", creator="MediThread")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    data_b = buf.getvalue()
    return data_b, max(1, data_b.count(b"/Type /Page\n") or data_b.count(b"/Type /Page "))
