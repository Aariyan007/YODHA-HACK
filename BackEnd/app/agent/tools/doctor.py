"""Phase 12-13: Doctor Agent tools. Same registry, same executor, same permission manager: a doctor's agent can only touch a
patient with an ACTIVE care link (checked on every call). The agent flags and prepares; it never decides. Where two records
disagree it says "verify" and shows both sources: it never picks one."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from ai import safety
from ...labs import lab_name, lab_status
from ...models import Alert, Consultation, Document, Medicine, Observation, Patient, ShareLink
from ..context import AgentContext
from ..executor import ToolError
from ..permissions import AgentPermissionManager
from ..registry import tool
from ..types import L2, L3, block
from .patient_read import condition_names

DOC = ("doctor",)


def _docs(ctx: AgentContext):
    q = select(Document).where(Document.patient_id == ctx.patient_id)
    allowed = AgentPermissionManager.doc_types(ctx)
    return q.where(Document.type.in_(allowed)) if allowed is not None else q


def _ev(d: Document) -> dict:
    return {"kind": "document", "id": d.id, "title": d.title, "date": d.date}


@tool("doctor.changes_since_visit", "What changed in the record since the last visit (or a given date): new records, results that moved, new medicines, new warnings.",
      {"type": "object", "properties": {"since": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$", "maxLength": 10}}, "additionalProperties": False},
      permission="records:read", roles=DOC, audit_category="doctor")
def changes_since_visit(ctx: AgentContext, args: dict) -> dict:
    last = ctx.db.scalar(select(Document.date).where(Document.patient_id == ctx.patient_id, Document.type.in_(("visit", "consultation")))
                         .order_by(Document.date.desc()))
    since = args.get("since") or last
    basis = f"since the last visit on {since}" if since and not args.get("since") else f"since {since}" if since else None
    if since is None:
        since = (date.today() - timedelta(days=90)).isoformat()
        basis = "in the last 90 days (no earlier visit is on record)"
    blocks = [block("text", text=f"Changes {basis}.")]
    ev: list[dict] = []
    new_docs = list(ctx.db.scalars(_docs(ctx).where(Document.date > since).order_by(Document.date.desc())))
    for d in new_docs[:8]:
        blocks.append(block("timeline_event", id=d.id, title=d.title, date=d.date, docType=d.type, status=d.status))
        ev.append(_ev(d))
    obs = list(ctx.db.scalars(select(Observation).where(Observation.patient_id == ctx.patient_id).order_by(Observation.date)))
    by: dict[str, list[Observation]] = {}
    for o in obs:
        by.setdefault(o.code, []).append(o)
    moved = 0
    for code, rows in by.items():
        after = [o for o in rows if o.date > since]
        before = [o for o in rows if o.date <= since]
        if after and before:
            a, b = before[-1], after[-1]
            blocks.append(block("comparison", name=lab_name(code, b.name), unit=b.unit, before={"date": a.date, "value": a.value},
                                after={"date": b.date, "value": b.value}, change=round(b.value - a.value, 2), points=2,
                                status=lab_status(code, b.value, b.ref_range)))
            moved += 1
        elif after:
            b = after[-1]
            blocks.append(block("metric", code=code, name=lab_name(code, b.name), value=b.value, unit=b.unit, date=b.date,
                                status=lab_status(code, b.value, b.ref_range), range=b.ref_range, documentId=b.document_id))
    for m in ctx.db.scalars(select(Medicine).where(Medicine.patient_id == ctx.patient_id, Medicine.active.is_(True), Medicine.start_date > since)):
        blocks.append(block("medication", id=m.id, name=m.name, dose=m.dose, frequency=m.frequency, times=m.times or [], instructions=None,
                            prescribedBy=m.prescribed_by, startDate=m.start_date, durationDays=m.duration_days, active=True))
    cutoff = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
    for a in ctx.db.scalars(select(Alert).where(Alert.patient_id == ctx.patient_id, Alert.resolved.is_(False), Alert.kind.not_in(("handwriting",)))):
        ca = a.created_at if a.created_at.tzinfo else a.created_at.replace(tzinfo=timezone.utc)
        if ca > cutoff:
            blocks.append(block("warning", severity=a.severity, title=a.title, text=a.message))
    if len(blocks) == 1:
        blocks.append(block("text", text="Nothing new has been recorded in that time."))
    return {"data": {"since": since, "newRecords": len(new_docs), "resultsMoved": moved}, "blocks": blocks, "evidence": ev}


def _conflicts(ctx: AgentContext) -> list[dict]:
    p = ctx.db.get(Patient, ctx.patient_id)
    meds = list(ctx.db.scalars(select(Medicine).where(Medicine.patient_id == ctx.patient_id, Medicine.active.is_(True))))
    docs = {d.id: d for d in ctx.db.scalars(select(Document).where(Document.patient_id == ctx.patient_id))}
    out: list[dict] = []

    def src(m: Medicine) -> str:
        d = docs.get(m.document_id)
        return f"{d.title}, {d.date}" if d else "no source record"

    seen: dict[str, list[Medicine]] = {}
    for m in meds:
        seen.setdefault(safety.to_generic(m.name) or (m.generic or m.name).lower(), []).append(m)
    for g, rows in seen.items():
        if len(rows) > 1:
            doses = {(r.dose or "").replace(" ", "").lower() for r in rows}
            kind = "different doses" if len(doses) > 1 else "listed twice"
            out.append({"title": f"{g.title()} is {kind}", "text": " vs ".join(f"{r.name} {r.dose or ''} ({src(r)})".replace("  ", " ") for r in rows),
                        "docs": [r.document_id for r in rows if r.document_id]})
    for m in meds:
        g = safety.to_generic(m.name) or (m.generic or "").lower()
        fam = safety.allergy_hit(g, p.allergies or []) if g else None
        if fam:
            out.append({"title": f"{m.name} and a recorded {fam} allergy", "text": f"{m.name} ({src(m)}) is in the {fam} family; the profile lists: {', '.join(map(str, p.allergies))}.",
                        "docs": [m.document_id] if m.document_id else []})
    gens = [(m, safety.to_generic(m.name) or (m.generic or "").lower()) for m in meds]
    for i in range(len(gens)):
        for j in range(i + 1, len(gens)):
            (a, ga), (b, gb) = gens[i], gens[j]
            if ga and gb and ga != gb and (hit := safety.check_pair_level(ga, gb)):
                out.append({"title": f"{a.name} with {b.name}: possible interaction ({hit[0]})", "text": f"{a.name} ({src(a)}) and {b.name} ({src(b)}). {hit[1]}",
                            "docs": [x for x in (a.document_id, b.document_id) if x]})
    by: dict[tuple[str, str], list[Observation]] = {}
    for o in ctx.db.scalars(select(Observation).where(Observation.patient_id == ctx.patient_id)):
        by.setdefault((o.code, o.date), []).append(o)
    for (code, d), rows in by.items():
        if len({r.value for r in rows}) > 1:
            out.append({"title": f"{lab_name(code, rows[0].name)} has two values on {d}",
                        "text": " vs ".join(f"{r.value:g} ({docs[r.document_id].title if r.document_id in docs else 'no source'})" for r in rows),
                        "docs": [r.document_id for r in rows if r.document_id]})
    return out


@tool("doctor.record_conflicts", "Find places where the patient's records disagree (medicine doses, allergies, interactions, results). The doctor verifies; nothing is chosen.",
      permission="records:read", roles=DOC, audit_category="doctor")
def record_conflicts(ctx: AgentContext, args: dict) -> dict:
    found = _conflicts(ctx)
    docs = {d.id: d for d in ctx.db.scalars(_docs(ctx))}
    ev = [_ev(docs[i]) for c in found for i in c["docs"] if i in docs]
    blocks = [block("warning", severity="medium", title="Please verify: " + c["title"], text=c["text"]) for c in found[:8]]
    return {"data": {"count": len(found)}, "blocks": blocks or [block("text", text="I found no disagreement between the records.")], "evidence": ev}


def _age_days(d: str) -> int:
    return (date.today() - date.fromisoformat(d)).days


@tool("doctor.missing_info", "Hints about information that is missing from the record (allergies, recent tests, follow-up). Hints only, not orders.",
      permission="records:read", roles=DOC, audit_category="doctor")
def missing_info(ctx: AgentContext, args: dict) -> dict:
    p = ctx.db.get(Patient, ctx.patient_id)
    conds = " ".join(condition_names(p)).lower()
    latest: dict[str, str] = {}
    for o in ctx.db.scalars(select(Observation).where(Observation.patient_id == ctx.patient_id).order_by(Observation.date)):
        latest[o.code] = o.date
    meds = [(safety.to_generic(m.name) or (m.generic or "")).lower() for m in ctx.db.scalars(select(Medicine).where(Medicine.patient_id == ctx.patient_id, Medicine.active.is_(True)))]
    hints = []
    if not (p.allergies or []):
        hints.append("No allergies are recorded. Confirm with the patient whether there are none.")
    if "diabet" in conds and ("hba1c" not in latest or _age_days(latest["hba1c"]) > 180):
        hints.append("Diabetes is listed but there is no HbA1c in the last 6 months.")
    if re.search(r"hypertens|blood pressure", conds) and ("sbp" not in latest or _age_days(latest["sbp"]) > 90):
        hints.append("Hypertension is listed but there is no blood pressure reading in the last 3 months.")
    if "metformin" in meds and not ({"creatinine", "egfr"} & set(latest)):
        hints.append("The patient takes metformin and there is no kidney test (creatinine or eGFR) on record.")
    if "weight" not in latest:
        hints.append("No weight is recorded.")
    last = ctx.db.scalar(_docs(ctx).where(Document.type.in_(("visit", "consultation"))).order_by(Document.date.desc()))
    if last is not None and not last.followup:
        hints.append(f"The last visit note ({last.date}) has no follow-up plan recorded.")
    blocks = [block("text", text="Possible gaps to ask about: " + str(len(hints)))] + [block("text", text=f"{i}. {h}") for i, h in enumerate(hints, 1)] if hints else \
        [block("text", text="I found no obvious gaps from the rules I check.")]
    return {"data": {"count": len(hints)}, "blocks": blocks}


@tool("doctor.brief", "Pre-visit brief: who the patient is, conditions, allergies, current medicines, latest results, warnings, last visit.",
      permission="records:read", level=L2, roles=DOC, audit_category="summary")
def doctor_brief(ctx: AgentContext, args: dict) -> dict:
    p = ctx.db.get(Patient, ctx.patient_id)
    from ...routers.patients import build_health_check
    hc = build_health_check(ctx.db, p, use_ai=False, for_doctor=True)
    blocks = [block("text", text=f"{p.name}" + (f", {p.age}" if p.age else "") + (f", {p.gender}" if p.gender else "") + ".")]
    if condition_names(p):
        blocks.append(block("text", text="Conditions: " + ", ".join(condition_names(p)) + "."))
    blocks.append(block("text", text=("Allergies: " + ", ".join(map(str, p.allergies))) if p.allergies else "Allergies: none recorded."))
    for m in ctx.db.scalars(select(Medicine).where(Medicine.patient_id == ctx.patient_id, Medicine.active.is_(True))):
        blocks.append(block("medication", id=m.id, name=m.name, dose=m.dose, frequency=m.frequency, times=m.times or [], instructions=None,
                            prescribedBy=m.prescribed_by, startDate=m.start_date, durationDays=m.duration_days, active=True))
    latest: dict[str, Observation] = {}
    for o in ctx.db.scalars(select(Observation).where(Observation.patient_id == ctx.patient_id).order_by(Observation.date)):
        latest[o.code] = o
    for o in sorted(latest.values(), key=lambda o: o.date, reverse=True)[:6]:
        blocks.append(block("metric", code=o.code, name=lab_name(o.code, o.name), value=o.value, unit=o.unit, date=o.date,
                            status=lab_status(o.code, o.value, o.ref_range), range=o.ref_range, documentId=o.document_id))
    for r in hc["risks"][:4]:
        blocks.append(block("warning", severity=r.get("level"), title=r.get("title"), text=r.get("message") or r.get("detail"), emergency=bool(r.get("emergency"))))
    last = ctx.db.scalar(_docs(ctx).where(Document.type.in_(("visit", "consultation"))).order_by(Document.date.desc()))
    if last is not None:
        blocks.append(block("text", text=f"Last visit: {last.date}, {last.title}." + (f" Follow-up: {last.followup}" if last.followup else "")))
    return {"data": {"risks": len(hc["risks"])}, "blocks": blocks, "evidence": [_ev(last)] if last else []}


# ---------------------------------------------------------------- consultation draft (needs the doctor's approval before saving)

@tool("consult.draft_from_notes", "Turn the doctor's typed or dictated notes into a draft visit note (SOAP) with flags. Nothing is saved to the patient's record.",
      {"type": "object", "properties": {"notes": {"type": "string", "minLength": 10, "maxLength": 4000}}, "required": ["notes"], "additionalProperties": False},
      permission="consult:draft", level=L2, roles=DOC, audit_category="consult", slow=True)
def consult_draft(ctx: AgentContext, args: dict) -> dict:
    from ...routers import consultations as C
    from ...models import User
    doctor = ctx.db.get(User, ctx.actor_id)
    link = ShareLink(token=__import__("secrets").token_urlsafe(16), patient_id=ctx.patient_id, scope="full", doctor_user_id=ctx.actor_id,
                     expires_at=datetime.now(timezone.utc) + timedelta(hours=8))
    ctx.db.add(link)
    c = Consultation(patient_id=ctx.patient_id, doctor_name=doctor.name, transcript="", transcript_lines=[], soap=dict(C.consult_ai.EMPTY_SOAP),
                     final_note={}, flags=[], questions=[], edited_fields=[], status="active", share_token=link.token)
    ctx.db.add(c)
    ctx.db.flush()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?\n])\s+", args["notes"]) if s.strip()][:40]
    for s in sentences:
        C._append_line(ctx.db, c, s[:1000], "doctor")
    out = C.finalize(c.id, ctx.db, link.token)  # the same finalize the console uses: SOAP + classification, status "draft"
    note = out.get("finalNote") or {}
    blocks = [block("text", text="Draft visit note. It is NOT saved to the patient's record until you approve it.")]
    for k, label in (("subjective", "Subjective"), ("objective", "Objective"), ("assessment", "Assessment"), ("plan", "Plan")):
        t = (note.get(k) or {}).get("text")
        if t:
            blocks.append(block("text", text=f"{label}: {t}"))
    for f in (c.flags or [])[:6]:
        blocks.append(block("warning", severity=f.get("severity"), title=f.get("title"), text=f.get("reason")))
    return {"data": {"consultationId": c.id}, "target": c.id, "ref": c.id, "blocks": blocks,
            "evidence": [], "_token": link.token}


def _draft(ctx: AgentContext, cid: str) -> Consultation:
    c = ctx.db.scalar(select(Consultation).where(Consultation.id == cid, Consultation.patient_id == ctx.patient_id))
    link = ctx.db.get(ShareLink, c.share_token) if c else None
    if c is None or link is None or link.doctor_user_id != ctx.actor_id:  # not this doctor's draft: same answer as missing
        raise ToolError("I could not find that draft.")
    if c.status == "approved":
        raise ToolError("That visit is already approved.")
    if c.status != "draft":
        raise ToolError("That visit has no draft note yet.")
    return c


def _approve_preview(ctx: AgentContext, args: dict) -> list[dict]:
    c = _draft(ctx, args["consultationId"])
    note = c.final_note or {}
    rows = [{"label": label, "value": (note.get(k) or {}).get("text") or "-"} for k, label in
            (("subjective", "Subjective"), ("objective", "Objective"), ("assessment", "Assessment"), ("plan", "Plan"))]
    cls = note.get("classification") or {}
    rows += [{"label": "Medicine", "value": f"{m.get('name')} ({m.get('action')})"} for m in cls.get("medicines", [])]
    rows.append({"label": "Effect", "value": "This is saved to the patient's health thread under your name, medicines are updated and the patient is notified."})
    return rows


@tool("consult.approve_draft", "Approve a draft visit note and save it to the patient's record.",
      {"type": "object", "properties": {"consultationId": {"type": "string", "minLength": 1, "maxLength": 32}}, "required": ["consultationId"], "additionalProperties": False},
      permission="consult:approve", level=L3, confirmation_required=True, roles=DOC, audit_category="consult", preview=_approve_preview,
      verify=lambda ctx, a, out: ctx.db.get(Consultation, a["consultationId"]).status == "approved")
def consult_approve(ctx: AgentContext, args: dict) -> dict:
    from ...routers import consultations as C
    c = _draft(ctx, args["consultationId"])
    out = C.approve(c.id, C.ApproveBody(), ctx.db, c.share_token)
    doc_id = (out.get("record") or {}).get("id") or c.document_id
    return {"data": {"documentId": doc_id}, "target": c.id, "ref": doc_id,
            "blocks": [block("text", text="Saved to the patient's health thread.")]}
