"""Phase 7: reading a file the person gave the agent. Extraction (L2: draft, stored on the file row, never on the health
thread), entities, evidence, summary and comparison with earlier results. All read from the stored extraction, so the
numbers shown always carry the document line they came from."""
from __future__ import annotations

from sqlalchemy import select

from ai.extractor import ExtractError, extract as _gemini_extract
from ...labs import code_for_name, lab_name, lab_range, lab_status, slug
from ...models import AgentFile, Medicine, Observation
from ... import vault
from .. import extract as ex, ingest
from ..context import AgentContext
from ..executor import ToolError
from ..registry import tool
from ..types import L2, block

EXTRACTOR = _gemini_extract  # tests replace this; production uses Gemini
FILE_ARG = {"type": "object", "properties": {"fileId": {"type": "string", "minLength": 1, "maxLength": 32}},
            "required": ["fileId"], "additionalProperties": False}


def _file(ctx: AgentContext, file_id: str) -> AgentFile:
    f = ctx.db.scalar(select(AgentFile).where(AgentFile.id == file_id, AgentFile.patient_id == ctx.patient_id,
                                              AgentFile.uploaded_by == ctx.actor_id, AgentFile.status != "discarded"))
    if f is None:  # missing and not-yours look the same
        raise ToolError("I could not find that file.")
    return f


def _need_extraction(ctx: AgentContext, f: AgentFile) -> dict:
    if not f.extraction:
        raise ToolError("I have not read this file yet. Ask me to read it first.")
    return f.extraction


def _evidence_list(x: dict) -> list[dict]:
    out = []
    for kind in ("diagnoses", "medicines", "observations", "vitals"):
        for it in x.get(kind, []):
            e = it.get("evidence") or {}
            out.append({"kind": "file_line", "id": f"{kind}:{e.get('lines')}", "title": it.get("name") or it.get("text"),
                        "page": e.get("page"), "lines": e.get("lines"), "quote": e.get("quote")})
    return out


@tool("documents.extract", "Read an attached file and list the diagnoses, medicines, results and vitals it contains, each with the line it came from. Saves nothing to the health thread.",
      {"type": "object", "properties": {"fileId": {"type": "string", "minLength": 1, "maxLength": 32}, "force": {"type": "boolean"}},
       "required": ["fileId"], "additionalProperties": False},
      permission="records:read", level=L2, audit_category="extract", slow=True, roles=("patient", "doctor"))
def documents_extract(ctx: AgentContext, args: dict) -> dict:
    f = _file(ctx, args["fileId"])
    if f.extraction and not args.get("force"):
        x = f.extraction
        return {"data": {"cached": True, "type": x.get("docType")}, "target": f.id,
                "blocks": [block("text", text=f"I already read {f.display_name}.")], "evidence": _evidence_list(x)[:20]}
    try:
        data = vault.get(f.storage_key, f.id, f.patient_id)
    except vault.VaultError:
        raise ToolError("I could not open that file.")
    pages, _ = ingest.pdf_pages(data) if f.mime == "application/pdf" else ([], 0)
    try:
        doc = EXTRACTOR(data, f.mime)
    except ExtractError as e:
        raise ToolError(str(e))
    lines = ex.lines_for(pages, doc.get("source_lines") or [])
    checked = ex.verify(doc, lines)
    items = checked["items"]
    found = any(items[k] for k in ("diagnoses", "medicines", "observations", "vitals"))
    text_cls = ingest.classify("\n".join(pages)) if any(pages) else None
    cls = ex.classification_check(doc.get("type"), text_cls, found)
    if f.classification and f.classification.get("source") == "user":
        cls = f.classification  # the person's own answer always wins
    clean = checked["clean_doc"]
    clean.pop("source_lines", None)
    f.extraction = {"docType": cls.get("type") or doc.get("type"), "date": doc.get("date_of_record"), "doctor": doc.get("doctor"),
                    "hospital": doc.get("hospital"), "followUp": doc.get("follow_up"), **items, "unverified": checked["unverified"],
                    "warnings": checked["warnings"], "lines": lines[:300], "cleanDoc": clean}
    f.classification = {**(f.classification or {}), **cls}
    f.status = "extracted"
    blocks = []
    if cls.get("type") is None:
        blocks.append(block("warning", severity="medium", title="I am not sure what this is", text=cls.get("reason") or "Please tell me what kind of document it is."))
    for w in checked["warnings"]:
        blocks.append(block("warning", severity="medium", title="Instructions inside the document ignored", text=w))
    if checked["unverified"]:
        blocks.append(block("warning", severity="low", title="Not found in the document text, so left out",
                            text=", ".join(u["text"] for u in checked["unverified"][:6])))
    blocks.append(block("text", text=f"Read {f.display_name}: {len(items['observations'])} results, {len(items['medicines'])} medicines, "
                                       f"{len(items['diagnoses'])} diagnoses. Nothing was added to your health thread."))
    return {"data": {"cached": False, "type": cls.get("type"), "needsType": cls.get("type") is None}, "target": f.id,
            "blocks": blocks, "evidence": _evidence_list(f.extraction)[:20]}


@tool("documents.entities", "List what a read file contains: diagnoses, medicines, results, vitals.", FILE_ARG,
      permission="records:read", audit_category="documents", roles=("patient", "doctor"))
def documents_entities(ctx: AgentContext, args: dict) -> dict:
    f = _file(ctx, args["fileId"])
    x = _need_extraction(ctx, f)
    blocks = []
    for d in x.get("diagnoses", []):
        blocks.append(block("warning", severity="low", title="Diagnosis written", text=d["text"], evidence=d["evidence"]))
    for m in x.get("medicines", []):
        blocks.append(block("medication", name=m["name"], dose=m.get("dose"), frequency=m.get("schedule"), times=[], instructions=m.get("purpose"),
                            evidence=m["evidence"], sample=False))
    for o in x.get("observations", []):
        code = code_for_name(o["name"]) or slug(o["name"])
        blocks.append(block("metric", code=code, name=lab_name(code, o["name"]), value=o["value"], unit=o.get("unit"), date=x.get("date"),
                            status=lab_status(code, o["value"], o.get("range")), range=lab_range(code) or o.get("range"), evidence=o["evidence"]))
    for v in x.get("vitals", []):
        blocks.append(block("metric", code=v["name"].lower(), name=v["name"], value=v["value"], unit=None, date=x.get("date"), status="steady",
                            range=None, evidence=v["evidence"]))
    return {"data": {"count": len(blocks)}, "target": f.id, "blocks": blocks or [block("text", text="I found nothing I can point to in this file.")],
            "evidence": _evidence_list(x)[:20]}


@tool("documents.evidence", "Show the exact lines of the file behind a result, medicine or diagnosis.",
      {"type": "object", "properties": {"fileId": {"type": "string", "minLength": 1, "maxLength": 32}, "about": {"type": "string", "maxLength": 80}},
       "required": ["fileId"], "additionalProperties": False},
      permission="records:read", audit_category="documents", roles=("patient", "doctor"))
def documents_evidence(ctx: AgentContext, args: dict) -> dict:
    f = _file(ctx, args["fileId"])
    x = _need_extraction(ctx, f)
    q = (args.get("about") or "").lower()
    ev = [e for e in _evidence_list(x) if not q or q in str(e["title"]).lower()]
    blocks = [block("evidence", documentId=f.id, page=e["page"], lines=e["lines"], quote=e["quote"], label=e["title"]) for e in ev[:10]]
    return {"data": {"count": len(ev)}, "target": f.id, "blocks": blocks or [block("text", text="I found no matching line in the file.")], "evidence": ev[:10]}


@tool("documents.summarize", "Summarise a read file in plain words, using only what it says.", FILE_ARG,
      permission="records:read", level=L2, audit_category="documents", roles=("patient", "doctor"))
def documents_summarize(ctx: AgentContext, args: dict) -> dict:
    f = _file(ctx, args["fileId"])
    x = _need_extraction(ctx, f)
    kind = {"lab": "lab report", "prescription": "prescription", "visit": "visit note", "scan": "scan report"}.get(x.get("docType"), "document")
    head = f"This is a {kind}" + (f" dated {x['date']}" if x.get("date") else "") + (f" from {x['hospital']}" if x.get("hospital") else "") + "."
    parts = []
    for o in x.get("observations", []):
        code = code_for_name(o["name"]) or slug(o["name"])
        st = lab_status(code, o["value"], o.get("range"))
        parts.append(f"{lab_name(code, o['name'])} {o['value']:g}{(' ' + o['unit']) if o.get('unit') else ''}" + ("" if st == "good" else " (outside the usual range)"))
    if x.get("medicines"):
        parts.append("medicines: " + ", ".join(m["name"] + (f" {m['dose']}" if m.get("dose") else "") for m in x["medicines"]))
    if x.get("diagnoses"):
        parts.append("diagnoses written: " + ", ".join(d["text"] for d in x["diagnoses"]))
    if x.get("followUp"):
        parts.append(f"follow-up: {x['followUp']}")
    blocks = [block("text", text=head), *[block("text", text=p.capitalize() + ".") for p in parts[:8]]]
    return {"data": {"points": len(parts)}, "target": f.id, "blocks": blocks, "evidence": _evidence_list(x)[:12]}


@tool("documents.compare", "Compare the results and medicines in a read file with what is already on the health thread.", FILE_ARG,
      permission="records:read", level=L2, audit_category="documents", roles=("patient", "doctor"))
def documents_compare(ctx: AgentContext, args: dict) -> dict:
    f = _file(ctx, args["fileId"])
    x = _need_extraction(ctx, f)
    blocks, firsts = [], []
    for o in x.get("observations", []):
        code = code_for_name(o["name"]) or slug(o["name"])
        prev = ctx.db.scalars(select(Observation).where(Observation.patient_id == ctx.patient_id, Observation.code == code)
                              .order_by(Observation.date.desc())).first()
        if prev is None:
            firsts.append(lab_name(code, o["name"]))
            continue
        blocks.append(block("comparison", name=lab_name(code, o["name"]), unit=o.get("unit") or prev.unit,
                            before={"date": prev.date, "value": prev.value}, after={"date": x.get("date") or "this file", "value": o["value"]},
                            change=round(o["value"] - prev.value, 2), points=2, evidence=o["evidence"]))
    active = {m.name.lower() for m in ctx.db.scalars(select(Medicine).where(Medicine.patient_id == ctx.patient_id, Medicine.active.is_(True)))}
    for m in x.get("medicines", []):
        state = "already on your list" if m["name"].lower() in active else "not on your current list"
        blocks.append(block("text", text=f"{m['name']}: {state}."))
    if firsts:
        blocks.append(block("text", text="No earlier result to compare for: " + ", ".join(firsts) + "."))
    return {"data": {"compared": len(blocks)}, "target": f.id, "blocks": blocks or [block("text", text="There is nothing in this file to compare.")],
            "evidence": _evidence_list(x)[:12]}
