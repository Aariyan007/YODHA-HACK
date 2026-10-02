"""Phase 11: patient write actions. Every tool here is L3: the executor parks it, shows the person exactly what will change
(`preview`), and runs the handler only after /confirm. Each has a `verify` that checks the world afterwards, so "done" is only
said when it is true. Medicine changes are L4 and have no tool at all (the planner answers them with an explanation)."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ai import pipeline
from ... import store, vault
from ...models import AccessLog, AgentFile, CareLink, Document, Medicine, Observation, Patient, ShareLink, User
from ...schemas import VitalsIn, document_out, iso
from ..context import AgentContext
from ..executor import ToolError
from ..registry import tool
from ..types import L3, block
from .patient_read import share_ref


class _NullBus:
    def send(self, obj: dict) -> None:
        pass


# ---------------------------------------------------------------- add a read file to the health thread

def _extracted(ctx: AgentContext, file_id: str) -> tuple[AgentFile, dict]:
    f = ctx.db.scalar(select(AgentFile).where(AgentFile.id == file_id, AgentFile.patient_id == ctx.patient_id, AgentFile.status.in_(("extracted", "confirmed"))))
    if f is None or not f.extraction:
        raise ToolError("I have not read that file yet, so there is nothing to add.")
    if f.status == "confirmed" or f.document_id:
        raise ToolError("This file is already on your health thread.")
    if not (f.classification or {}).get("type"):
        raise ToolError("Tell me what kind of document this is first (lab report, prescription, visit note or scan).")
    dup = ctx.db.scalar(select(Document).where(Document.patient_id == ctx.patient_id, Document.file_hash == f.sha256))
    if dup is not None:
        raise ToolError("A record from this exact file is already on your health thread.")
    return f, f.extraction


def _add_preview(ctx: AgentContext, args: dict) -> list[dict]:
    f, x = _extracted(ctx, args["fileId"])
    rows = [{"label": "Adds to your thread", "value": f"{(f.classification or {}).get('type')} dated {x.get('date') or 'today (no date found)'}"}]
    rows += [{"label": "Diagnosis written", "value": d["text"]} for d in x.get("diagnoses", [])]
    rows += [{"label": "Medicine", "value": m["name"] + (f" {m['dose']}" if m.get("dose") else "")} for m in x.get("medicines", [])]
    rows += [{"label": "Result", "value": f"{o['name']} {o['value']:g} {o.get('unit') or ''}".strip()} for o in x.get("observations", [])]
    if x.get("unverified"):
        rows.append({"label": "Left out (not in the text)", "value": ", ".join(u["text"] for u in x["unverified"][:5])})
    rows.append({"label": "Also", "value": "Medicines and results are checked for interactions, allergies and warnings, and reminders can follow."})
    return rows


@tool("records.add_from_file", "Add what was read from the attached file to your health thread.",
      {"type": "object", "properties": {"fileId": {"type": "string", "minLength": 1, "maxLength": 32}}, "required": ["fileId"], "additionalProperties": False},
      permission="records:write", level=L3, confirmation_required=True, audit_category="write", preview=_add_preview,
      verify=lambda ctx, a, out: ctx.db.scalar(select(Document).where(Document.id == (out.get("data") or {}).get("documentId"), Document.patient_id == ctx.patient_id)) is not None)
def records_add_from_file(ctx: AgentContext, args: dict) -> dict:
    f, x = _extracted(ctx, args["fileId"])
    doc = dict(x["cleanDoc"])
    doc["type"] = (f.classification or {}).get("type")
    doc["source_lines"] = [l["text"] for l in x.get("lines", [])]
    try:
        data = vault.get(f.storage_key, f.id, f.patient_id)
    except vault.VaultError:
        raise ToolError("I could not open the file again to add it.")
    ctx.db.commit()  # release our transaction: the pipeline saves with its own session
    result = pipeline._run_sync(ctx.patient_id, data, "agent-file." + ("pdf" if f.mime == "application/pdf" else "png"), f.sha256, _NullBus(), doc=doc)
    rec = result["record"]
    f.status, f.document_id = "confirmed", rec["id"]
    ctx.db.add(AccessLog(patient_id=ctx.patient_id, who=ctx.actor_name, role="Patient", action=f"Added {rec['type']} with the agent", via="Agent"))
    blocks = [block("timeline_event", id=rec["id"], title=rec["title"], date=rec["date"], docType=rec["type"], status=rec["status"])]
    blocks += [block("warning", severity=a["severity"], title=a["title"], text=a["message"]) for a in result.get("alerts", [])[:6]]
    return {"data": {"documentId": rec["id"], "alerts": len(result.get("alerts", []))}, "target": rec["id"], "ref": rec["id"], "blocks": blocks,
            "evidence": [{"kind": "document", "id": rec["id"], "title": rec["title"], "date": rec["date"]}]}


# ---------------------------------------------------------------- sharing: QR / revoke

def _share_preview(ctx: AgentContext, args: dict) -> list[dict]:
    scope = args.get("scope", "full")
    what = {"full": "all your records", "labs": "your lab reports only", "medicines": "your prescriptions only"}[scope]
    return [{"label": "Shares", "value": what}, {"label": "For", "value": f"{args.get('hours', 24)} hours"},
            {"label": "Who can open it", "value": "Anyone who scans the QR code or has the link, until it expires or you stop it."}]


@tool("sharing.create", "Create a share link and QR code for a doctor to scan.",
      {"type": "object", "properties": {"scope": {"type": "string", "enum": ["full", "labs", "medicines"]},
                                        "hours": {"type": "integer", "minimum": 1, "maximum": 72}}, "additionalProperties": False},
      permission="sharing:write", level=L3, confirmation_required=True, audit_category="sharing", preview=_share_preview,
      verify=lambda ctx, a, out: ctx.db.scalar(select(ShareLink).where(ShareLink.patient_id == ctx.patient_id, ShareLink.token == out["_token"])) is not None)
def sharing_create(ctx: AgentContext, args: dict) -> dict:
    from ...routers.shares import make_share
    link = make_share(ctx.db, ctx.patient_id, args.get("scope", "full"), args.get("hours", 24))
    ref = share_ref(link.token)
    # The token is a secret: it is NOT put in the task result, the audit log or the response. The browser fetches it once,
    # with the person's login, from GET /api/agent/shares/{ref} while this short-lived key exists.
    store.set_value(f"agent:qr:{ctx.patient_id}:{ref}", json.dumps({"url": f"/share/{link.token}", "scope": link.scope, "expiresAt": iso(link.expires_at)}), ttl=15 * 60)
    ctx.db.add(AccessLog(patient_id=ctx.patient_id, who=ctx.actor_name, role="Patient", action=f"Made a {link.scope} share link", via="Agent"))
    return {"data": {"ref": ref, "scope": link.scope}, "_token": link.token, "target": ref, "ref": ref,
            "blocks": [block("action", kind="show_qr", ref=ref, scope=link.scope, expiresAt=iso(link.expires_at))]}


def _active_links(ctx: AgentContext) -> list[ShareLink]:
    now = datetime.now(timezone.utc)
    out = []
    for s in ctx.db.scalars(select(ShareLink).where(ShareLink.patient_id == ctx.patient_id, ShareLink.doctor_user_id.is_(None))):
        exp = s.expires_at if s.expires_at.tzinfo else s.expires_at.replace(tzinfo=timezone.utc)
        if exp > now:
            out.append(s)
    return out


def _revoke_targets(ctx: AgentContext, args: dict) -> list[ShareLink]:
    links = _active_links(ctx)
    if args.get("ref"):
        links = [s for s in links if share_ref(s.token) == args["ref"]]
    elif not args.get("all"):
        raise ToolError("Tell me which share link to stop, or say stop all sharing.")
    if not links:
        raise ToolError("There is no active share link to stop.")
    return links


@tool("sharing.revoke", "Stop one or all active share links so they no longer open.",
      {"type": "object", "properties": {"ref": {"type": "string", "maxLength": 20}, "all": {"type": "boolean"}}, "additionalProperties": False},
      permission="sharing:write", level=L3, confirmation_required=True, audit_category="sharing",
      preview=lambda ctx, a: [{"label": "Stops", "value": f"{len(_revoke_targets(ctx, a))} share link(s)"}, {"label": "Effect", "value": "Anyone holding the link or QR will see an error. This cannot be undone, but you can make a new one."}],
      verify=lambda ctx, a, out: not any(ctx.db.get(ShareLink, t) for t in out["_tokens"]))
def sharing_revoke(ctx: AgentContext, args: dict) -> dict:
    links = _revoke_targets(ctx, args)
    tokens = [s.token for s in links]
    for s in links:
        ctx.db.delete(s)
    ctx.db.add(AccessLog(patient_id=ctx.patient_id, who=ctx.actor_name, role="Patient", action=f"Stopped {len(links)} share link(s)", via="Agent"))
    ctx.db.flush()
    return {"data": {"stopped": len(links)}, "_tokens": tokens, "target": args.get("ref") or "all",
            "blocks": [block("text", text=f"Stopped {len(links)} share link{'s' if len(links) != 1 else ''}. They no longer open.")]}


def _linked_doctor(ctx: AgentContext, name: str):
    q = (name or "").lower().replace("dr.", "").replace("dr ", "").strip()
    found = []
    for l in ctx.db.scalars(select(CareLink).where(CareLink.patient_id == ctx.patient_id, CareLink.status == "active")):
        u = ctx.db.get(User, l.doctor_user_id)
        if q and q in u.name.lower():
            found.append((l, u))
    if not found:
        raise ToolError("I could not find a doctor with access that matches that name.")
    if len(found) > 1:
        raise ToolError("More than one doctor matches. Please give the full name.")
    return found[0]


@tool("care.revoke_doctor", "Remove a doctor's access to your record.",
      {"type": "object", "properties": {"name": {"type": "string", "minLength": 2, "maxLength": 80}}, "required": ["name"], "additionalProperties": False},
      permission="sharing:write", level=L3, confirmation_required=True, audit_category="sharing",
      preview=lambda ctx, a: [{"label": "Removes access for", "value": _linked_doctor(ctx, a["name"])[1].name},
                              {"label": "Effect", "value": "They can no longer open your record or start a visit. You can invite them again."}],
      verify=lambda ctx, a, out: ctx.db.get(CareLink, out["_link"]).status == "revoked")
def care_revoke_doctor(ctx: AgentContext, args: dict) -> dict:
    from ...routers.care import revoke_link
    link, user = _linked_doctor(ctx, args["name"])
    revoke_link(ctx.db, ctx.db.get(Patient, ctx.patient_id), link.id)
    ctx.db.flush()
    return {"data": {"doctor": user.name}, "_link": link.id, "target": link.id,
            "blocks": [block("text", text=f"{user.name} no longer has access to your record.")]}


# ---------------------------------------------------------------- care loop: mark a dose taken

def _dose(ctx: AgentContext, args: dict) -> dict:
    from ...routers.patients import build_reminders, today
    name = (args.get("medicine") or "").lower().strip()
    rows = [r for r in build_reminders(ctx.db, ctx.patient_id, today()) if name and name in r["name"].lower()]
    if args.get("time"):
        rows = [r for r in rows if r["time"] == args["time"]]
    rows = [r for r in rows if not r["taken"]]
    if not rows:
        raise ToolError("I found no dose of that medicine waiting to be marked today.")
    if len(rows) > 1:
        raise ToolError("Which dose? It is due at " + " and ".join(r["time"] for r in rows) + ". Say the time.")
    return rows[0]


@tool("careloop.mark_taken", "Mark one of today's doses as taken.",
      {"type": "object", "properties": {"medicine": {"type": "string", "minLength": 2, "maxLength": 60}, "time": {"type": "string", "maxLength": 5}},
       "required": ["medicine"], "additionalProperties": False},
      permission="careloop:write", level=L3, confirmation_required=True, audit_category="careloop",
      preview=lambda ctx, a: [{"label": "Mark as taken", "value": f"{(d := _dose(ctx, a))['name']} {d['dose'] or ''} at {d['time']} today".replace('  ', ' ')},
                              {"label": "Effect", "value": "No missed-dose message will be sent for it."}],
      verify=lambda ctx, a, out: store.get_value(out["_key"]) is not None)
def careloop_mark_taken(ctx: AgentContext, args: dict) -> dict:
    from ... import reminder_service
    from ...routers.patients import today
    d = _dose(ctx, args)
    reminder_service.mark_taken(ctx.db, ctx.patient_id, d["key"], today())
    return {"data": {"key": d["key"]}, "_key": f"taken:{ctx.patient_id}:{today()}:{d['key']}", "target": d["key"],
            "blocks": [block("care_item", key=d["key"], name=d["name"], dose=d["dose"], time=d["time"], taken=True)]}


# ---------------------------------------------------------------- log a home reading

READING_FIELDS = {"sbp": "BP top", "dbp": "BP bottom", "pulse": "Pulse", "spo2": "Oxygen", "weight": "Weight", "temp": "Temperature", "sugar": "Sugar"}
READING_SCHEMA = {"type": "object", "properties": {
    "sbp": {"type": "number", "minimum": 50, "maximum": 300}, "dbp": {"type": "number", "minimum": 30, "maximum": 200},
    "pulse": {"type": "number", "minimum": 20, "maximum": 250}, "spo2": {"type": "number", "minimum": 50, "maximum": 100},
    "weight": {"type": "number", "minimum": 2, "maximum": 300}, "temp": {"type": "number", "minimum": 90, "maximum": 110},
    "sugar": {"type": "number", "minimum": 20, "maximum": 800}, "sugarType": {"type": "string", "enum": ["fbs", "ppbs", "rbs"]}},
    "additionalProperties": False}


def _reading_preview(ctx: AgentContext, args: dict) -> list[dict]:
    if (args.get("sbp") is None) != (args.get("dbp") is None):
        raise ToolError("I need both blood pressure numbers (top and bottom).")
    rows = [{"label": READING_FIELDS[k], "value": f"{args[k]:g}" + (f" ({args.get('sugarType', 'rbs')})" if k == "sugar" else "")} for k in READING_FIELDS if args.get(k) is not None]
    if not rows:
        raise ToolError("I did not find a reading to add.")
    return rows + [{"label": "Date", "value": "today"}, {"label": "Check these numbers", "value": "I took them from your words. Say no if any is wrong."}]


@tool("health.log_reading", "Add a home reading (blood pressure, pulse, oxygen, weight, temperature or sugar) to your health thread.",
      READING_SCHEMA, permission="records:write", level=L3, confirmation_required=True, audit_category="write", preview=_reading_preview,
      verify=lambda ctx, a, out: ctx.db.scalar(select(Document).where(Document.id == out["data"]["documentId"], Document.patient_id == ctx.patient_id)) is not None)
def health_log_reading(ctx: AgentContext, args: dict) -> dict:
    from ...routers.patients import add_vitals
    _reading_preview(ctx, args)
    body = VitalsIn(**args)
    patient = ctx.db.get(Patient, ctx.patient_id)
    out = add_vitals(body, patient, ctx.db)  # the same code path (and danger checks) as the Log a reading form
    rec = out["record"]
    blocks = [block("timeline_event", id=rec["id"], title=rec["title"], date=rec["date"], docType="vitals", status=rec.get("status"))]
    blocks += [block("warning", severity=r.get("level"), title=r.get("title"), text=r.get("message") or r.get("detail"),
                     emergency=bool(r.get("emergency"))) for r in out["risks"][:3]]
    return {"data": {"documentId": rec["id"]}, "target": rec["id"], "ref": rec["id"], "blocks": blocks}
