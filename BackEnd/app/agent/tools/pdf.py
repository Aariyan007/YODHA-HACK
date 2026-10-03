"""Phase 10: PDF generation (L2: creates a private file for the person, changes nothing in the record). Stored encrypted in
the vault like any other file; download needs the person's login and is never cached."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ...labs import lab_name, lab_status
from ...models import Alert, AgentFile, Document, Medicine, Observation, Patient
from ... import vault
from .. import pdfgen
from ..context import AgentContext
from ..executor import ToolError
from ..permissions import AgentPermissionManager
from ..registry import tool
from ..types import L2, block

KINDS = ["patient_summary", "medication_summary", "visit_prep", "doctor_brief"]
BY_ROLE = {"patient": {"patient_summary", "medication_summary", "visit_prep"}, "doctor": {"doctor_brief"}}
TTL_HOURS = 24


def _data(ctx: AgentContext) -> dict:
    db = ctx.db
    p = db.get(Patient, ctx.patient_id)
    docs = {d.id: d for d in db.scalars(select(Document).where(Document.patient_id == ctx.patient_id))}
    allowed = AgentPermissionManager.doc_types(ctx)

    def src(doc_id):
        d = docs.get(doc_id)
        return (d.title, d.date) if d and (allowed is None or d.type in allowed) else (None, None)

    meds = []
    for m in db.scalars(select(Medicine).where(Medicine.patient_id == ctx.patient_id, Medicine.active.is_(True))):
        t, d = src(m.document_id)
        meds.append({"name": m.name, "dose": m.dose, "frequency": m.frequency, "times": m.times or [], "prescribedBy": m.prescribed_by,
                     "sourceTitle": t, "sourceDate": d})
    latest: dict[str, Observation] = {}
    for o in db.scalars(select(Observation).where(Observation.patient_id == ctx.patient_id).order_by(Observation.date)):
        latest[o.code] = o
    labs = []
    for o in sorted(latest.values(), key=lambda o: o.date, reverse=True)[:14]:
        t, d = src(o.document_id)
        labs.append({"name": lab_name(o.code, o.name), "value": o.value, "unit": o.unit, "date": o.date,
                     "status": {"good": "usual", "watch": "watch", "alert": "needs attention"}.get(lab_status(o.code, o.value, o.ref_range), "-"),
                     "sourceTitle": t, "sourceDate": d})
    alerts = [{"title": a.title, "message": a.message} for a in db.scalars(select(Alert).where(Alert.patient_id == ctx.patient_id, Alert.resolved.is_(False), Alert.kind.not_in(("handwriting",))))]
    records = [{"title": d.title, "date": d.date, "type": d.type} for d in sorted(docs.values(), key=lambda d: d.date, reverse=True)
               if allowed is None or d.type in allowed]
    from ...routers.patients import build_health_check
    questions = [q["text"] for q in build_health_check(db, p, use_ai=False)["review"].get("askDoctor", [])]
    return {"patient": {"name": p.name, "age": p.age, "gender": p.gender, "bloodGroup": p.blood_group,
                        "conditions": __import__("app.agent.tools.patient_read", fromlist=["condition_names"]).condition_names(p), "allergies": p.allergies or []},
            "medicines": meds, "labs": labs, "alerts": alerts, "records": records, "questions": questions}


@tool("pdf.generate", "Create a PDF summary from the record: health summary, medication list, or visit preparation. Every fact has a source. Saves nothing to the health thread.",
      {"type": "object", "properties": {"kind": {"type": "string", "enum": KINDS}}, "required": ["kind"], "additionalProperties": False},
      permission="pdf:create", level=L2, roles=("patient", "doctor"), audit_category="pdf", verify=lambda c, a, o: _verify(c, a, o))
def pdf_generate(ctx: AgentContext, args: dict) -> dict:
    if not vault.available():
        raise ToolError("File storage is not set up, so I cannot make a private PDF.")
    if args["kind"] not in BY_ROLE[ctx.role]:
        raise ToolError("That kind of PDF is not available to you.")
    payload = _data(ctx)
    if args["kind"] == "doctor_brief":
        from . import doctor as D
        payload["conflicts"] = D._conflicts(ctx)
        payload["gaps"] = []
    data, pages = pdfgen.build(args["kind"], payload)
    name = {"patient_summary": "Health summary", "medication_summary": "Medication summary", "visit_prep": "Visit preparation", "doctor_brief": "Pre-visit brief"}[args["kind"]] \
        + f" {datetime.now().date().isoformat()}.pdf"
    import hashlib
    row = AgentFile(patient_id=ctx.patient_id, uploaded_by=ctx.actor_id, uploader_role=ctx.role, display_name=name, mime="application/pdf",
                    size=len(data), sha256=hashlib.sha256(data).hexdigest(), storage_key=vault.new_storage_key(), status="generated",
                    classification={"type": "generated", "kind": args["kind"], "confidence": 1.0, "source": "agent",
                                    "expiresAt": (datetime.now(timezone.utc) + timedelta(hours=TTL_HOURS)).isoformat()})
    ctx.db.add(row)
    ctx.db.flush()
    vault.put(row.storage_key, data, row.id, ctx.patient_id)
    return {"data": {"fileId": row.id, "kind": args["kind"]}, "target": row.id, "ref": row.id,
            "blocks": [block("pdf", fileId=row.id, name=name, kind=args["kind"], size=len(data), pages=pages,
                             expiresInHours=TTL_HOURS)],
            }


def _verify(ctx: AgentContext, args: dict, out: dict) -> bool:
    """The file exists, decrypts, and is a PDF: only then does the agent say it made one."""
    row = ctx.db.get(AgentFile, (out.get("data") or {}).get("fileId"))
    try:
        return bool(row) and vault.get(row.storage_key, row.id, row.patient_id).startswith(b"%PDF-")
    except vault.VaultError:
        return False


@tool("pdf.preview", "Show the first lines of a PDF the agent made, before the person downloads it.",
      {"type": "object", "properties": {"fileId": {"type": "string", "minLength": 1, "maxLength": 32}}, "required": ["fileId"],
       "additionalProperties": False},
      permission="pdf:create", level=L2, roles=("patient", "doctor"), audit_category="pdf")
def pdf_preview(ctx: AgentContext, args: dict) -> dict:
    from .. import ingest
    row = ctx.db.scalar(select(AgentFile).where(AgentFile.id == args["fileId"], AgentFile.patient_id == ctx.patient_id, AgentFile.uploaded_by == ctx.actor_id, AgentFile.status == "generated"))
    if row is None:
        raise ToolError("I could not find that PDF.")
    pages, _ = ingest.pdf_pages(vault.get(row.storage_key, row.id, row.patient_id))
    lines = [l["text"] for l in ingest.text_lines(pages)][:14]
    return {"data": {"lines": len(lines)}, "target": row.id, "blocks": [block("text", text=l) for l in lines]}
