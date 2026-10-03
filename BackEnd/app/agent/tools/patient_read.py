"""Read-only (L1) and navigation (L2) tools. They use the same builders as the REST routes, so the agent sees exactly
what the app sees. Scope applies here too: a labs-only share can never read prescriptions through the agent.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ...labs import lab_name, lab_range, lab_status
from ...models import Alert, Document, Medicine, Observation, Patient, SentDose, ShareLink
from ...risk import assess
from ...schemas import document_out, iso, medicine_out
from ..context import AgentContext
from ..executor import ToolError
from ..permissions import AgentPermissionManager
from ..registry import tool
from ..types import L2, block

ROLES = ("patient", "doctor")
DOC_TYPES = ["lab", "prescription", "consultation", "visit", "scan", "vitals"]


def condition_names(p: Patient) -> list[str]:
    """Conditions are stored as {name, ...} objects (ICD-10 imports add more fields), older rows may be plain strings."""
    return [str(c.get("name")) if isinstance(c, dict) else str(c) for c in (p.conditions or []) if (c.get("name") if isinstance(c, dict) else c)]


def share_ref(token: str) -> str:
    """A handle for a share link that isn't the token (safe to show and log)."""
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()[:10]


def _docs(ctx: AgentContext):
    """Document query limited to this patient and what the scope allows."""
    q = select(Document).where(Document.patient_id == ctx.patient_id)
    allowed = AgentPermissionManager.doc_types(ctx)
    if allowed is not None:
        q = q.where(Document.type.in_(allowed))
    return q


def _doc_block(d: Document) -> dict:
    return block("document", id=d.id, title=d.title, date=d.date, docType=d.type, status=d.status,
                 summary=(d.summary or "")[:400] or None, provider=d.provider or d.source, doctor=d.doctor)


def _ev(d: Document) -> dict:
    return {"kind": "document", "id": d.id, "title": d.title, "date": d.date}


def _metric_block(o: Observation) -> dict:
    return block("metric", code=o.code, name=lab_name(o.code, o.name), value=o.value, unit=o.unit, date=o.date,
                 status=lab_status(o.code, o.value, o.ref_range), range=lab_range(o.code) or o.ref_range,
                 documentId=o.document_id)


# ---------------- documents / timeline

@tool("timeline.list", "List the most recent records on the health thread.",
      {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20},
                                        "type": {"type": "string", "enum": DOC_TYPES}}, "additionalProperties": False},
      permission="records:read", roles=ROLES, audit_category="timeline")
def timeline_list(ctx: AgentContext, args: dict) -> dict:
    q = _docs(ctx)
    if args.get("type"):
        q = q.where(Document.type == args["type"])
    docs = list(ctx.db.scalars(q.order_by(Document.date.desc(), Document.created_at.desc()).limit(args.get("limit", 5))))
    blocks = [_doc_block(d) for d in docs] or [block("text", text="There are no records on the thread yet.")]
    return {"data": {"count": len(docs), "ids": [d.id for d in docs]}, "blocks": blocks, "evidence": [_ev(d) for d in docs]}


@tool("documents.search", "Search records by words in the title, tags, provider, doctor or summary; filter by type and dates.",
      {"type": "object", "properties": {
          "query": {"type": "string", "minLength": 1, "maxLength": 80}, "type": {"type": "string", "enum": DOC_TYPES},
          "since": {"type": "string", "maxLength": 10}, "until": {"type": "string", "maxLength": 10},
          "limit": {"type": "integer", "minimum": 1, "maximum": 20}}, "required": ["query"], "additionalProperties": False},
      permission="records:read", roles=ROLES, audit_category="documents")
def documents_search(ctx: AgentContext, args: dict) -> dict:
    words = [w for w in args["query"].lower().split() if len(w) > 1]
    q = _docs(ctx)
    if args.get("type"):
        q = q.where(Document.type == args["type"])
    if args.get("since"):
        q = q.where(Document.date >= args["since"])
    if args.get("until"):
        q = q.where(Document.date <= args["until"])
    hits = []
    for d in ctx.db.scalars(q.order_by(Document.date.desc())):
        hay = " ".join(str(x or "") for x in (d.title, d.provider, d.doctor, d.source, d.summary, " ".join(d.tags or []),
                                              " ".join(str(i.get("name", "")) for i in (d.items or [])))).lower()
        score = sum(w in hay for w in words)
        if score:
            hits.append((score, d))
    hits.sort(key=lambda t: (-t[0], t[1].date), reverse=False)
    docs = [d for _, d in hits[:args.get("limit", 8)]]
    blocks = [_doc_block(d) for d in docs] or [block("text", text=f"I found no record matching \"{args['query']}\".")]
    return {"data": {"count": len(docs), "ids": [d.id for d in docs]}, "blocks": blocks, "evidence": [_ev(d) for d in docs]}


@tool("documents.get", "Get one record in full by its id.",
      {"type": "object", "properties": {"id": {"type": "string", "minLength": 1, "maxLength": 32}}, "required": ["id"],
       "additionalProperties": False},
      permission="records:read", roles=ROLES, audit_category="documents")
def documents_get(ctx: AgentContext, args: dict) -> dict:
    d = ctx.db.scalar(_docs(ctx).where(Document.id == args["id"]))
    if d is None:  # same answer for "missing" and "not yours", so ids cannot be probed
        raise ToolError("I could not find that record.")
    full = document_out(d)
    return {"data": full, "target": d.id,
            "blocks": [_doc_block(d)] + [block("evidence", documentId=d.id, line=l) for l in (d.source_lines or [])[:8]],
            "evidence": [_ev(d)]}


# ---------------- medications

@tool("medications.list", "List the current medicines with dose, timing and prescriber.",
      permission="meds:read", roles=ROLES, audit_category="medications")
def medications_list(ctx: AgentContext, args: dict) -> dict:
    meds = list(ctx.db.scalars(select(Medicine).where(Medicine.patient_id == ctx.patient_id, Medicine.active.is_(True))))
    blocks = [block("medication", **medicine_out(m)) for m in meds] or [block("text", text="No current medicines are recorded.")]
    ev = [{"kind": "medicine", "id": m.id, "title": m.name, "documentId": m.document_id} for m in meds]
    return {"data": {"count": len(meds)}, "blocks": blocks, "evidence": ev}


# ---------------- health data

@tool("health.latest", "Latest value of every lab and vital, with status against the reference range.",
      permission="health:read", roles=ROLES, audit_category="health")
def health_latest(ctx: AgentContext, args: dict) -> dict:
    latest: dict[str, Observation] = {}
    for o in ctx.db.scalars(select(Observation).where(Observation.patient_id == ctx.patient_id).order_by(Observation.date)):
        latest[o.code] = o
    obs = sorted(latest.values(), key=lambda o: o.date, reverse=True)[:12]
    blocks = [_metric_block(o) for o in obs] or [block("text", text="No lab or vital results are recorded yet.")]
    ev = [{"kind": "observation", "id": o.id, "title": lab_name(o.code, o.name), "date": o.date, "documentId": o.document_id}
          for o in obs]
    return {"data": {"count": len(obs)}, "blocks": blocks, "evidence": ev}


@tool("health.trend", "All stored values of one test over time (codes such as hba1c, sbp, dbp, fbs, ldl, creatinine, pulse, weight).",
      {"type": "object", "properties": {"code": {"type": "string", "minLength": 1, "maxLength": 40}}, "required": ["code"],
       "additionalProperties": False},
      permission="health:read", roles=ROLES, audit_category="health")
def health_trend(ctx: AgentContext, args: dict) -> dict:
    codes = [args["code"].lower()] + (["dbp"] if args["code"].lower() == "sbp" else [])
    rows = list(ctx.db.scalars(select(Observation).where(
        Observation.patient_id == ctx.patient_id, Observation.code.in_(codes)).order_by(Observation.date)))
    if not rows:
        return {"data": {"count": 0}, "blocks": [block("text", text="I have no stored results for that test.")]}
    first, last = rows[0], rows[-1]
    blocks = [_metric_block(o) for o in rows[-8:]]
    if len([o for o in rows if o.code == last.code]) >= 2:
        same = [o for o in rows if o.code == last.code]
        a, b = same[0], same[-1]
        blocks.append(block("comparison", name=lab_name(b.code, b.name), unit=b.unit,
                            before={"date": a.date, "value": a.value}, after={"date": b.date, "value": b.value},
                            change=round(b.value - a.value, 2), points=len(same)))
    ev = [{"kind": "observation", "id": o.id, "title": lab_name(o.code, o.name), "date": o.date, "documentId": o.document_id}
          for o in rows[-8:]]
    return {"data": {"count": len(rows), "from": first.date, "to": last.date}, "blocks": blocks, "evidence": ev}


@tool("health.conditions", "The conditions listed on the profile.", permission="health:read", roles=ROLES, audit_category="health")
def health_conditions(ctx: AgentContext, args: dict) -> dict:
    items = condition_names(ctx.db.get(Patient, ctx.patient_id))
    text = ("Conditions on file: " + ", ".join(map(str, items)) + ".") if items else "No conditions are listed on the profile."
    return {"data": {"conditions": items}, "blocks": [block("text", text=text)]}


@tool("health.allergies", "The allergies listed on the profile.", permission="health:read", roles=ROLES, audit_category="health")
def health_allergies(ctx: AgentContext, args: dict) -> dict:
    items = list(ctx.db.get(Patient, ctx.patient_id).allergies or [])
    text = ("Allergies on file: " + ", ".join(map(str, items)) + ".") if items else "No allergies are listed on the profile."
    return {"data": {"allergies": items}, "blocks": [block("text", text=text)]}


@tool("health.alerts", "Open warnings from checks on medicines and results.", permission="health:read", roles=ROLES,
      audit_category="health")
def health_alerts(ctx: AgentContext, args: dict) -> dict:
    rows = [a for a in ctx.db.scalars(select(Alert).where(Alert.patient_id == ctx.patient_id, Alert.resolved.is_(False), *([Alert.kind.not_in(("handwriting",))] if ctx.role == "doctor" else [])))]
    order = {"high": 0, "medium": 1, "low": 2}
    rows.sort(key=lambda a: order.get(a.severity, 9))
    blocks = [block("warning", id=a.id, severity=a.severity, kind=a.kind, title=a.title, text=a.message) for a in rows[:8]]
    return {"data": {"count": len(rows)}, "blocks": blocks or [block("text", text="There are no open warnings.")]}


@tool("health.risks", "Danger checks over the whole record (rules, not AI).", permission="health:read", roles=ROLES,
      audit_category="health")
def health_risks(ctx: AgentContext, args: dict) -> dict:
    risks = assess(ctx.db, ctx.patient_id)
    blocks = [block("warning", severity=r.get("level"), title=r.get("title"), text=r.get("message") or r.get("detail"),
                    specialist=r.get("specialist"), emergency=bool(r.get("emergency"))) for r in risks[:5]]
    return {"data": {"count": len(risks), "emergency": any(r.get("emergency") for r in risks)}, "blocks": blocks}


# ---------------- care loop

@tool("careloop.due", "Doses due today and whether each was marked taken.", permission="careloop:read", roles=ROLES,
      audit_category="careloop")
def careloop_due(ctx: AgentContext, args: dict) -> dict:
    from ...routers.patients import build_reminders, today
    rows = build_reminders(ctx.db, ctx.patient_id, today())
    blocks = [block("care_item", key=r["key"], name=r["name"], dose=r["dose"], time=r["time"], taken=r["taken"],
                    instructions=r["instructions"]) for r in rows]
    left = sum(not r["taken"] for r in rows)
    return {"data": {"total": len(rows), "notTaken": left},
            "blocks": blocks or [block("text", text="No doses are scheduled today.")]}


@tool("careloop.history", "Doses reminded, taken and missed over the last days.",
      {"type": "object", "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 30}}, "additionalProperties": False},
      permission="careloop:read", roles=ROLES, audit_category="careloop")
def careloop_history(ctx: AgentContext, args: dict) -> dict:
    since = (datetime.now() - timedelta(days=args.get("days", 7))).date().isoformat()
    rows = list(ctx.db.scalars(select(SentDose).where(SentDose.patient_id == ctx.patient_id, SentDose.date >= since)))
    taken = sum(r.taken for r in rows)
    text = f"Since {since}: {len(rows)} dose reminders, {taken} marked taken, {len(rows) - taken} not marked taken."
    return {"data": {"reminded": len(rows), "taken": taken}, "blocks": [block("text", text=text)]}


# ---------------- doctors

def _nearby_blocks(ctx: AgentContext, specialty=None, language=None, city=None, limit=4, emergency=False) -> tuple[list[dict], dict]:
    from ... import doctors as finder
    p = ctx.db.get(Patient, ctx.patient_id)
    origin = finder.resolve_origin(None, None, city, p.lat, p.lng, p.city)
    spec = specialty if specialty in finder.SPECIALTIES else None
    lang = language if language in finder.LANGUAGES else None
    found = finder.search(origin, spec, lang, None, False, emergency, None, None, None, False, limit)
    blocks = [block("doctor_match", id=d.get("id"), name=d.get("name"), specialty=d.get("specialties") or d.get("specialty"),
                    hospital=d.get("clinic") or d.get("hospital"), distanceKm=d.get("distanceKm"), rating=d.get("rating"),
                    sample=True) for d in found["results"]]
    if blocks:
        src = {"default": "a default starting point (Kochi). Set your town in your profile or use the Doctors page for exact distances",
               "profile": "your saved town", "city": "the town you chose", "device": "your location"}.get(origin.get("source"), "your area")
        blocks.insert(0, block("text", text=f"Distances are from {origin.get('label')} ({src}). These are sample listings, not real clinics."))
    return blocks, origin


@tool("doctors.search", "Find doctors in the (sample) directory by specialty, language or city, nearest first. Use emergency=true for the nearest hospital / emergency / casualty.",
      {"type": "object", "properties": {"specialty": {"type": "string", "maxLength": 60}, "language": {"type": "string", "maxLength": 20},
                                        "city": {"type": "string", "maxLength": 60}, "limit": {"type": "integer", "minimum": 1, "maximum": 8},
                                        "emergency": {"type": "boolean"}}, "additionalProperties": False},
      permission="doctors:read", audit_category="doctors")
def doctors_search(ctx: AgentContext, args: dict) -> dict:
    blocks, origin = _nearby_blocks(ctx, args.get("specialty"), args.get("language"), args.get("city"), args.get("limit", 4), bool(args.get("emergency")))
    if not blocks:
        blocks = [block("text", text="I found no doctor matching that in the sample directory.")]
    return {"data": {"count": sum(b["type"] == "doctor_match" for b in blocks), "origin": origin.get("label")}, "blocks": blocks}


# ---------------- sharing (read)

@tool("sharing.active", "List the share links that are still active (no tokens are shown).", permission="sharing:read",
      audit_category="sharing")
def sharing_active(ctx: AgentContext, args: dict) -> dict:
    now = datetime.now(timezone.utc)
    rows = []
    for s in ctx.db.scalars(select(ShareLink).where(ShareLink.patient_id == ctx.patient_id, ShareLink.doctor_user_id.is_(None))):
        exp = s.expires_at if s.expires_at.tzinfo else s.expires_at.replace(tzinfo=timezone.utc)
        if exp > now:
            rows.append({"ref": share_ref(s.token), "scope": s.scope, "expiresAt": iso(exp)})
    text = (f"{len(rows)} share link(s) active." if rows else "No share links are active.")
    return {"data": {"count": len(rows), "links": rows},
            "blocks": [block("text", text=text)] + [block("care_item", key=r["ref"], name=f"Share ({r['scope']})", time=r["expiresAt"]) for r in rows]}


# ---------------- navigation (L2): the frontend carries out the structured action

PATIENT_ROUTES = {"/": "Home", "/timeline": "Health thread", "/medicines": "Medicines", "/reminders": "Reminders",
                  "/insights": "Health Check", "/upload": "Add a record", "/sharing": "Sharing", "/doctors": "Doctors",
                  "/profile": "Profile", "/triage": "Which doctor"}
DOCTOR_ROUTES = {"/doctor": "Your patients"}


ROUTE_WORDS = {"home": "/", "dashboard": "/", "timeline": "/timeline", "thread": "/timeline", "health thread": "/timeline", "records": "/timeline",
               "medicines": "/medicines", "medicine": "/medicines", "medications": "/medicines", "reminders": "/reminders",
               "health check": "/insights", "health": "/insights", "insights": "/insights", "upload": "/upload", "add": "/upload",
               "sharing": "/sharing", "share": "/sharing", "doctors": "/doctors", "doctor": "/doctors", "profile": "/profile",
               "which doctor": "/triage", "triage": "/triage", "patients": "/doctor"}


def _route(raw: str, routes: dict) -> str | None:
    """Accepts '/sharing', 'sharing', 'Sharing page', 'health thread' and so on. Only a known screen of this role comes out."""
    r = (raw or "").strip().lower().split("?")[0].split("#")[0]
    if r.startswith("http"):
        return None
    if ("/" + r.strip("/")) in routes:
        return "/" + r.strip("/") if r.strip("/") else "/"
    if r in ("/", ""):
        return "/" if "/" in routes else None
    if r.startswith("/"):  # a path has to be exact, only plain words get the friendly mapping
        return None
    word = re.sub(r"\b(page|tab|screen|the|my)\b", "", r.replace("/", " ")).strip()
    word = re.sub(r"\s+", " ", word)
    target = ROUTE_WORDS.get(word)
    return target if target in routes else None


@tool("navigation.navigate", "Take the person to a screen of the app. Routes: / (home), /timeline, /medicines, /reminders, /insights (health check), /upload, /sharing, /doctors, /profile, /triage; doctors: /doctor.",
      {"type": "object", "properties": {"route": {"type": "string", "maxLength": 60}, "focus": {"type": "string", "maxLength": 32}}, "required": ["route"],
       "additionalProperties": False},
      permission="nav:use", roles=ROLES, level=L2, audit_category="navigation")
def navigation_navigate(ctx: AgentContext, args: dict) -> dict:
    routes = PATIENT_ROUTES if ctx.role == "patient" else DOCTOR_ROUTES
    route = _route(args["route"], routes)
    if route is None:
        raise ToolError("I cannot open that screen.")
    return {"data": {"route": route}, "blocks": [block("navigation", route=route, label=routes[route], focus=args.get("focus"))], "target": route}


# ---------------- visit preparation (L2: a draft the person reads, nothing is saved)

@tool("visit.prepare", "Prepare for a doctor visit: what changed, what needs attention, and questions to ask. Uses rules over the record, not AI.",
      permission="health:read", level=L2, roles=ROLES, audit_category="summary")
def visit_prepare(ctx: AgentContext, args: dict) -> dict:
    from ...routers.patients import build_health_check
    p = ctx.db.get(Patient, ctx.patient_id)
    hc = build_health_check(ctx.db, p, use_ai=False)
    rev = hc["review"]
    blocks = [block("text", text=rev["headline"])]
    for pt in rev.get("points", [])[:5]:
        blocks.append(block("warning" if pt["kind"] in ("worse", "missing") else "text", severity="medium" if pt["kind"] in ("worse", "missing") else None,
                            title=pt["kind"].capitalize(), text=pt["text"]))
    for i, q in enumerate(rev.get("askDoctor", [])[:5], 1):
        blocks.append(block("text", text=f"Question {i}: {q['text']}"))
    meds = list(ctx.db.scalars(select(Medicine).where(Medicine.patient_id == ctx.patient_id, Medicine.active.is_(True))))
    if meds:
        blocks.append(block("text", text="Bring your medicine list: " + ", ".join(m.name for m in meds) + "."))
    if p.allergies:
        blocks.append(block("text", text="Tell them about your allergies: " + ", ".join(map(str, p.allergies)) + "."))
    return {"data": {"risks": len(hc["risks"]), "questions": len(rev.get("askDoctor", []))}, "blocks": blocks}


# ---------------- symptoms: the app's own triage (rules first), never a diagnosis

@tool("triage.check", "When the person describes a symptom or how they feel (pain, fever, breathless, dizzy...), check how urgent it sounds and which kind of doctor fits. Rules decide emergencies.",
      {"type": "object", "properties": {"text": {"type": "string", "minLength": 2, "maxLength": 500}}, "required": ["text"], "additionalProperties": False},
      permission="health:read", level=L2, audit_category="triage")
def triage_check(ctx: AgentContext, args: dict) -> dict:
    from ...routers.documents import TriageBody, triage
    r = triage(TriageBody(text=args["text"]))
    blocks = []
    if r.get("urgency") == "emergency":
        blocks.append(block("warning", severity="high", title="This may be an emergency", text=r["why"], emergency=True))
        near, _o = _nearby_blocks(ctx, emergency=True, limit=3)  # the nearest 24-hour care, right away
        blocks += near
    else:
        blocks.append(block("text", text=f"{r['why']} A {r['specialist']} is a good fit. This is guidance on who to see, not a diagnosis."))
    return {"data": {"urgency": r.get("urgency"), "specialist": r.get("specialist"), "emergency": bool(r.get("urgent"))}, "blocks": blocks}


# ---------------- medicine safety questions

@tool("medications.check_interactions", "Check the person's current medicines against each other and against their listed allergies for known bad combinations.",
      permission="meds:read", roles=ROLES, audit_category="medications")
def medications_check_interactions(ctx: AgentContext, args: dict) -> dict:
    from ai import safety
    meds = list(ctx.db.scalars(select(Medicine).where(Medicine.patient_id == ctx.patient_id, Medicine.active.is_(True))))
    p = ctx.db.get(Patient, ctx.patient_id)
    items = [(m, (safety.to_generic(m.name) or (m.generic or "").lower() or "").strip()) for m in meds]
    known = [(m, g) for m, g in items if g]
    blocks, found = [], 0
    for i in range(len(known)):
        for j in range(i + 1, len(known)):
            (a, ga), (b, gb) = known[i], known[j]
            if ga == gb:
                blocks.append(block("warning", severity="high", title=f"{a.name} and {b.name} look like the same medicine", text=f"Both are {ga}. Taking both doubles the dose. Ask your doctor which to continue."))
                found += 1
            elif hit := safety.check_pair_level(ga, gb):
                blocks.append(block("warning", severity=hit[0], title=f"{a.name} with {b.name}", text=hit[1]))
                found += 1
    for m, g in known:
        fam = safety.allergy_hit(g, list(p.allergies or []))
        if fam:
            blocks.append(block("warning", severity="high", title=f"{m.name} and your {fam} allergy", text=f"{m.name} belongs to the {fam} family and your profile lists an allergy to it. Ask your doctor or pharmacist before the next dose."))
            found += 1
    unchecked = [m.name for m, g in items if not g]
    head = (f"I checked {len(known)} medicine(s) against each other and your allergies: " + (f"{found} thing(s) to look at." if found else "I found no known bad combination.")) if len(known) >= 1 else "You have no current medicines to check."
    out = [block("text", text=head)] + blocks
    if unchecked:
        out.append(block("text", text="I could not check these because I do not recognise them as known drugs: " + ", ".join(unchecked) + ". Ask your pharmacist about them."))
    out.append(block("text", text="This uses the DDInter interaction database and curated rules. No result here is a guarantee, and you should never stop a medicine on your own: ask your doctor or pharmacist."))
    return {"data": {"checked": len(known), "found": found}, "blocks": out}


@tool("medications.side_effects", "Look up the common and serious side effects of the person's medicines (or the ones named) from the public FDA drug label. General information only.",
      {"type": "object", "properties": {"names": {"type": "array", "items": {"type": "string", "maxLength": 80}, "maxItems": 6}}, "additionalProperties": False},
      permission="meds:read", roles=ROLES, audit_category="medications", slow=True)
def medications_side_effects(ctx: AgentContext, args: dict) -> dict:
    from ai import drug_usage
    from ..llm import _groq_judge
    meds = list(ctx.db.scalars(select(Medicine).where(Medicine.patient_id == ctx.patient_id, Medicine.active.is_(True))))
    if args.get("names"):
        keys = [n.strip().lower() for n in args["names"]]
        meds = [m for m in meds if any(k in m.name.lower() or m.name.lower() in k for k in keys)]
        if not meds:
            raise ToolError("I could not find a current medicine with that name.")
    if not meds:
        return {"data": {"found": 0}, "blocks": [block("text", text="You have no current medicines recorded.")]}
    blocks, found = [], 0
    for m in meds[:5]:
        u = drug_usage.side_effects(m.name, extractor=_groq_judge)
        if not u:
            blocks.append(block("text", text=f"{m.name}: I could not find a public label for this (common for some Indian brands). Ask your pharmacist for the leaflet."))
            continue
        found += 1
        parts = []
        if u["hasText"] and not u["summarised"]:
            parts.append("I could not summarise the side-effects section right now, so ask your pharmacist for the full list.")
        if u["common"]:
            parts.append("Common, from the label: " + "; ".join(f'{i["effect"]} (“{i["quote"]}”)' for i in u["common"][:6]) + ".")
        if u["serious"]:
            parts.append("Get medical help or call your doctor for: " + "; ".join(f'{i["effect"]} (“{i["quote"]}”)' for i in u["serious"][:4]) + ".")
        if u["boxed"]:
            parts.append(f"The label also carries a boxed warning: “{u['boxed']}”")
        if not parts:
            parts.append("The label has a side-effects section but I could not summarise it right now. Please ask your pharmacist.")
        blocks.append(block("text", text=f"{m.name} ({u['generic']}): " + " ".join(parts)))
    blocks.append(block("text", text=f"Source: US FDA drug label (openFDA). This is general information, not a complete list, and not advice about your own case. Do not stop a medicine on your own: ask your doctor or pharmacist."))
    return {"data": {"found": found}, "blocks": blocks}
