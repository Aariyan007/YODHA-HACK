"""Doctor-side consultation flow.

Six endpoints:
    POST /api/consultations/start          start a visit from a share token
    POST /api/consultations/{id}/line      append one transcript line
    POST /api/consultations/{id}/finalize  build the full SOAP note (status=draft)
    POST /api/consultations/{id}/approve   doctor signs off; writes patient timeline
    GET  /api/consultations/{id}           full state for the review screen
    POST /api/consultations/demo/{id}      stage fallback: feed 14 scripted lines

Rules enforced:
- The AI never diagnoses. Assessment only restates the doctor.
- Nothing reaches the patient timeline before /approve.
- Every AI call has a 25 s cap; failure returns the transcript and an empty note.
"""
from __future__ import annotations

import re
import time as _time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai import consultation as consult_ai
from ai import reminders as reminders_mod
from ai.safety import allergy_hit, check_pair_level, to_generic

from ..database import get_db
from ..health_hooks import after_new_data, notify_patient
from ..labs import lab_range, lab_status, loinc_for
from ..models import AccessLog, Alert, Consultation, Document, Medicine, Observation, Patient, ShareLink, new_id
from ..vitals import from_text as vitals_from_text

router = APIRouter(prefix="/api/consultations", tags=["consultations"])


# ---------- request bodies ----------

class StartBody(BaseModel):
    patientToken: str = Field(min_length=4)
    doctorName: str | None = Field(default=None, max_length=120)


class LineBody(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    speaker: str = Field(default="unknown", pattern=r"^(doctor|patient|unknown)$")


class ApproveBody(BaseModel):
    edits: dict[str, Any] = Field(default_factory=dict)


# ---------- helpers ----------

EMERGENCY_WORDS = [
    (r"\bchest\s+pain\b|\bheart\s+attack\b", "chest pain"),
    (r"\bcan'?t\s+breathe\b|\bshort(ness)?\s+of\s+breath\b", "shortness of breath"),
    (r"\bface\s+droop\b|\bslurred\s+speech\b|\bweak\s+(on\s+)?one\s+side\b|\bstroke\b", "stroke symptoms"),
    (r"\bfaint(ing|ed)?\b|\bunconscious\b|\bpassed\s+out\b", "fainting"),
    (r"\bbleeding\s+heavily\b|\buncontroll(ed|able)\s+bleed", "heavy bleeding"),
    (r"\banaphylaxis\b|\bswollen\s+tongue\b", "severe allergy"),
]

DURATION_RE = re.compile(
    r"\b\d+\s*(day|days|week|weeks|month|months|year|years|hour|hours|hrs?)\b|\bsince\b",
    re.I,
)
ALLERGY_WORDS = re.compile(r"\ballerg(y|ic|ies)\b|\bno\s+allerg", re.I)
FOLLOWUP_WORDS = re.compile(
    r"\bfollow[-\s]?up\b|\bcome\s+back\b|\breview\s+(after|in)\b|\bsee\s+me\s+(in|after)\b",
    re.I,
)


def _get_consult(db: Session, cid: str) -> Consultation:
    row = db.get(Consultation, cid)
    if row is None:
        raise HTTPException(404, "Consultation not found")
    return row


def _validate_share(db: Session, token: str) -> ShareLink:
    link = db.get(ShareLink, token)
    if link is None:
        raise HTTPException(404, "Share link not found")
    expires = link.expires_at if link.expires_at.tzinfo else link.expires_at.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(410, "Share link expired")
    return link


def _authorize(db: Session, cid: str, token: str | None) -> Consultation:
    """Fetch the consultation and verify the share token still grants access."""
    if not token:
        raise HTTPException(401, "Missing X-Share-Token header")
    c = _get_consult(db, cid)
    if c.share_token != token:
        raise HTTPException(404, "Share link not found")  # same answer as a fake token: do not reveal the visit exists
    _validate_share(db, token)
    return c


def _active_meds(db: Session, patient_id: str) -> list[dict]:
    rows = db.scalars(select(Medicine).where(Medicine.patient_id == patient_id, Medicine.active.is_(True)))
    return [{"name": m.name, "generic": (m.generic or to_generic(m.name) or "").lower()} for m in rows]


_MED_TOKEN = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")


def _mentions_in_line(text: str, extra_known: list[dict]) -> list[dict]:
    """Return medicines mentioned in a line as [{name, generic}].

    Scans every word against BRAND_TO_GENERIC via to_generic, so patient-report
    strings like 'Metformin' and brand names like 'Glycomet' both hit.
    """
    out: dict[str, dict] = {}
    for tok in _MED_TOKEN.findall(text or ""):
        g = to_generic(tok)
        if g:
            out.setdefault(g, {"name": tok, "generic": g})
    # Also match two-word brand entries we know.
    for em in extra_known:
        g = em.get("generic")
        if g and re.search(rf"\b{re.escape(em['name'])}\b", text or "", re.I):
            out.setdefault(g, {"name": em["name"], "generic": g})
    return list(out.values())


def _flag(kind: str, severity: str, title: str, reason: str, line_index: int) -> dict:
    return {
        "id": new_id(),
        "kind": kind,
        "severity": severity,
        "title": title,
        "reason": reason,
        "lineIndex": line_index,
        "resolved": False,
    }


def _run_fast_checks(
    *,
    line: dict,
    line_index: int,
    patient: Patient,
    active_meds: list[dict],
    other_mentions: list[dict],   # meds seen earlier in the transcript
) -> list[dict]:
    """Pure-Python per-line safety checks. Returns new flags only."""
    out: list[dict] = []
    text = line.get("text", "")
    low = text.lower()

    # Emergency words
    for pat, label in EMERGENCY_WORDS:
        if re.search(pat, low):
            out.append(_flag(
                "urgent", "high",
                f"Possible {label}",
                f"The line \"{text}\" mentions {label}. Treat as urgent.",
                line_index,
            ))
            break  # one urgent flag per line is enough

    # Medicine-centric checks (doctor-spoken prescriptions matter most, but
    # we also run them on patient-spoken meds so historical duplicates surface).
    mentions = _mentions_in_line(text, active_meds)
    allergies = list(patient.allergies or [])

    for m in mentions:
        g = m["generic"]

        # Duplicate: same generic already in patient's active list
        dup = next((e for e in active_meds if e["generic"] == g), None)
        if dup is not None:
            out.append(_flag(
                "duplicate", "high",
                f"{m['name']} duplicates {dup['name']}",
                f"{m['name']} and {dup['name']} are both {g}. Doubling the dose can be unsafe.",
                line_index,
            ))

        # Allergy family hit
        hit = allergy_hit(g, allergies)
        if hit:
            out.append(_flag(
                "allergy", "high",
                f"Possible allergy: {m['name']}",
                f"{m['name']} ({g}) belongs to the {hit} family, which the patient is listed as allergic to.",
                line_index,
            ))

        # Clash: against active meds + any earlier transcript mentions
        universe = active_meds + other_mentions
        checked: set[tuple[str, str]] = set()
        for other in universe:
            og = (other.get("generic") or "").lower()
            if not og or og == g:
                continue
            key = tuple(sorted((g, og)))
            if key in checked:
                continue
            checked.add(key)
            hit = check_pair_level(g, og)
            if hit:
                sev, msg = hit
                out.append(_flag(
                    "clash", sev,
                    f"{m['name']} + {other['name']}",
                    f"{m['name']} ({g}) with {other['name']} ({og}): {msg}",
                    line_index,
                ))
    return out


def _missing_info_flags(lines: list[dict], has_flagged: set[str]) -> list[dict]:
    """Only runs once the transcript has 6+ lines. Each missing kind is added once."""
    if len(lines) < 6:
        return []
    joined = " ".join((ln.get("text") or "") for ln in lines)
    new: list[dict] = []

    if "missing_allergy" not in has_flagged and not ALLERGY_WORDS.search(joined):
        new.append(_flag(
            "missing", "medium",
            "Allergy history not mentioned",
            "The patient's allergy history has not been discussed in this visit.",
            len(lines) - 1,
        ) | {"kind_tag": "missing_allergy"})

    if "missing_duration" not in has_flagged and not DURATION_RE.search(joined):
        new.append(_flag(
            "missing", "medium",
            "Symptom duration not mentioned",
            "No duration (days/weeks/months) has been stated for the symptoms.",
            len(lines) - 1,
        ) | {"kind_tag": "missing_duration"})

    if "missing_followup" not in has_flagged and not FOLLOWUP_WORDS.search(joined):
        new.append(_flag(
            "missing", "low",
            "No follow-up set",
            "A follow-up plan has not been stated.",
            len(lines) - 1,
        ) | {"kind_tag": "missing_followup"})

    return new


def _patient_summary(patient: Patient, active: list[dict]) -> dict:
    return {
        "conditions": [c["name"] for c in (patient.conditions or [])],
        "allergies": list(patient.allergies or []),
        "medicines": [a["name"] for a in active],
    }


def _consultation_out(c: Consultation) -> dict:
    return {
        "id": c.id,
        "patientId": c.patient_id,
        "doctorName": c.doctor_name,
        "status": c.status,
        "transcript": c.transcript_lines or [],
        "soap": c.soap or {},
        "finalNote": c.final_note or {},
        "flags": c.flags or [],
        "questions": c.questions or [],
        "editedFields": c.edited_fields or [],
        "documentId": c.document_id,
        "createdAt": c.created_at.isoformat() if c.created_at else None,
    }


# ---------- endpoints ----------

@router.post("/start")
def start(body: StartBody, db: Session = Depends(get_db)):
    link = _validate_share(db, body.patientToken)
    patient = db.get(Patient, link.patient_id)
    doctor_name = (body.doctorName or "Dr. Rahul Das").strip()[:120] or "Dr. Rahul Das"

    c = Consultation(
        patient_id=patient.id,
        doctor_name=doctor_name,
        transcript="",
        transcript_lines=[],
        soap=dict(consult_ai.EMPTY_SOAP),
        final_note={},
        flags=[],
        questions=[],
        edited_fields=[],
        status="active",
        share_token=link.token,
    )
    db.add(c)
    db.add(AccessLog(
        patient_id=patient.id, who=doctor_name, role="Doctor",
        action="Started consultation", via="Share link",
    ))
    db.commit()
    db.refresh(c)
    return {"consultationId": c.id}


@router.post("/{cid}/line")
def add_line(
    cid: str, body: LineBody,
    db: Session = Depends(get_db),
    x_share_token: str | None = Header(default=None, alias="X-Share-Token"),
):
    c = _authorize(db, cid, x_share_token)
    if c.status == "approved":
        raise HTTPException(409, "Consultation already approved")
    patient = db.get(Patient, c.patient_id)

    # Resolve speaker
    speaker = body.speaker
    if speaker == "unknown":
        speaker = consult_ai.guess_speaker(body.text)

    lines = list(c.transcript_lines or [])
    line = {"speaker": speaker, "text": body.text.strip()}
    new_index = len(lines)
    lines.append(line)

    # ----- fast per-line checks -----
    active = _active_meds(db, c.patient_id)
    prior_mentions = [mm for ln in lines[:-1] for mm in _mentions_in_line(ln.get("text", ""), active)]
    existing_flags = list(c.flags or [])
    new_flags = _run_fast_checks(
        line=line, line_index=new_index, patient=patient,
        active_meds=active, other_mentions=prior_mentions,
    )
    existing_flags.extend(new_flags)

    # Missing-info flags (dedupe via kind_tag)
    tagged = {f.get("kind_tag") for f in existing_flags if f.get("kind_tag")}
    existing_flags.extend(_missing_info_flags(lines, tagged))

    # ----- partial SOAP + question suggestions every 3 lines -----
    partial = c.soap or dict(consult_ai.EMPTY_SOAP)
    suggestions = list(c.questions or [])
    if len(lines) % 3 == 0:
        partial = consult_ai.partial_soap(lines)
        suggestions = consult_ai.suggest_questions(lines, _patient_summary(patient, active))

    # Persist
    c.transcript_lines = lines
    c.transcript = "\n".join(f"{ln['speaker']}: {ln['text']}" for ln in lines)
    c.soap = partial
    c.flags = existing_flags
    c.questions = suggestions
    db.commit()
    db.refresh(c)

    return {
        "transcript": lines,
        "partial_note": partial,
        "flags": existing_flags,
        "suggestions": suggestions,
    }


@router.post("/{cid}/finalize")
def finalize(
    cid: str,
    db: Session = Depends(get_db),
    x_share_token: str | None = Header(default=None, alias="X-Share-Token"),
):
    c = _authorize(db, cid, x_share_token)
    if c.status == "approved":
        raise HTTPException(409, "Consultation already approved")
    lines = list(c.transcript_lines or [])
    final = consult_ai.final_soap(lines)
    c.final_note = final
    c.status = "draft"
    db.commit()
    db.refresh(c)
    return _consultation_out(c)


def _extract_medicines_from_plan(plan_text: str | None, lines: list[dict]) -> list[dict]:
    """Pull medicines from the plan text first, then fall back to any doctor
    lines that look like a prescription. Returns extractor-style dicts."""
    meds: dict[str, dict] = {}
    sources = [plan_text or ""]
    sources.extend(ln["text"] for ln in lines if ln.get("speaker") == "doctor")

    # Patterns like "Tab Glycomet 500 mg BD x 7 days" or "Clarithromycin 500mg twice daily"
    dose_re = re.compile(r"(\d+\s*mg|\d+\s*ml|\d+\s*mcg)", re.I)
    sched_re = re.compile(
        r"\b(OD|BD|TDS|QID|HS|SOS|PRN|\d\s*-\s*\d\s*-\s*\d|"
        r"once\s+daily|twice\s+daily|three\s+times\s+(?:a\s+)?daily|"
        r"four\s+times\s+(?:a\s+)?daily|every\s+\d+\s+hours?|at\s+night|at\s+bedtime)\b",
        re.I,
    )
    dur_re = re.compile(r"(?:x|for)\s*(\d+\s*(?:d|day|days|w|wk|week|weeks))", re.I)

    for src in sources:
        for tok in _MED_TOKEN.findall(src):
            g = to_generic(tok)
            if not g:
                continue
            if g in meds:
                continue
            # Snip a window around the token for dose/sched detection
            idx = src.lower().find(tok.lower())
            window = src[max(0, idx - 10): idx + 80] if idx >= 0 else src
            m_dose = dose_re.search(window)
            m_sched = sched_re.search(window)
            m_dur = dur_re.search(window)
            sched_raw = m_sched.group(1) if m_sched else None
            # Keep abbreviations uppercase (BD), natural phrases lowercase ("twice daily").
            if sched_raw and len(sched_raw) <= 4:
                sched_raw = sched_raw.upper()
            meds[g] = {
                "name": tok,
                "generic": g,
                "dose": m_dose.group(1) if m_dose else None,
                "schedule": sched_raw,
                "duration": m_dur.group(1) if m_dur else None,
                "purpose": None,
            }
    return list(meds.values())


@router.post("/{cid}/approve")
def approve(
    cid: str, body: ApproveBody,
    db: Session = Depends(get_db),
    x_share_token: str | None = Header(default=None, alias="X-Share-Token"),
):
    c = _authorize(db, cid, x_share_token)
    if c.status == "approved":
        raise HTTPException(409, "Consultation already approved")
    patient = db.get(Patient, c.patient_id)
    if patient is None:
        raise HTTPException(404, "Patient not found")

    final = dict(c.final_note or {})
    edited: list[str] = []
    for k in ("subjective", "objective", "assessment", "plan"):
        if k in body.edits:
            v = body.edits[k]
            if isinstance(v, dict):
                final[k] = {"text": v.get("text"), "source_lines": v.get("source_lines", (final.get(k) or {}).get("source_lines", []))}
            else:
                final[k] = {"text": v, "source_lines": (final.get(k) or {}).get("source_lines", [])}
            edited.append(k)

    lines = list(c.transcript_lines or [])
    plan_text = (final.get("plan") or {}).get("text")
    meds = _extract_medicines_from_plan(plan_text, lines)

    # Follow-up: pull a "review in N days" hint from the plan text if present
    follow_up = None
    if plan_text:
        m = re.search(r"(review|follow.?up|come\s+back)[^.]*", plan_text, re.I)
        if m:
            follow_up = m.group(0).strip().rstrip(".")

    # Patient-friendly summary (Groq EN + ML)
    summary = consult_ai.patient_summary(final)

    date_s = datetime.now().date().isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()
    doc_id = new_id()

    items = [{
        "name": m["name"], "generic": m["generic"], "dose": m.get("dose"),
        "frequency": m.get("schedule"), "duration": m.get("duration"), "purpose": m.get("purpose"),
    } for m in meds]
    # Readings the doctor said out loud ("BP is 150 by 95") or wrote in the Objective field.
    objective_text = (final.get("objective") or {}).get("text") or ""
    said = vitals_from_text("\n".join(ln["text"] for ln in lines if ln.get("speaker") == "doctor") + "\n" + objective_text)
    for v in said:
        v["status"] = lab_status(v["code"], v["value"])
        v["range"] = lab_range(v["code"])
    items = [{k: v[k] for k in ("name", "code", "value", "unit", "range", "status")} for v in said] + items

    db.add(Document(
        id=doc_id, patient_id=c.patient_id, date=date_s, type="visit",
        title=f"Visit with {c.doctor_name}", source=c.doctor_name,
        summary=summary["en"], summary_ml=summary["ml"],
        tags=[], items=items,
        status="good", provider=None, doctor=c.doctor_name,
        followup=follow_up,
        source_kind="transcript",
        source_lines=[f"{ln['speaker']}: {ln['text']}" for ln in lines],
        source_highlight=list(range(min(len(lines), 20))),
    ))

    for v in said:
        db.add(Observation(patient_id=c.patient_id, document_id=doc_id, date=date_s, code=v["code"],
                           name=v["name"], value=v["value"], unit=v["unit"], loinc=loinc_for(v["code"]), source="visit"))

    # Save medicines + build reminders
    for m in meds:
        times = reminders_mod.parse_schedule(m.get("schedule"))
        db.add(Medicine(
            patient_id=c.patient_id, document_id=doc_id,
            name=m["name"], generic=m["generic"], dose=m.get("dose"),
            frequency=m.get("schedule"), times=times,
            instructions=m.get("purpose"),
            start_date=date_s, prescribed_by=c.doctor_name,
            duration_days=reminders_mod.parse_duration_days(m.get("schedule"), m.get("duration")),
        ))
    rem_list = reminders_mod.build_reminders(meds, follow_up)

    # Save any still-open flags as Alerts
    open_flags = [f for f in (c.flags or []) if not f.get("resolved")]
    saved_alerts = []
    for f in open_flags:
        severity = f.get("severity", "medium")
        kind = f.get("kind", "clash")
        if kind == "urgent":
            kind = "clash"  # map to an existing Alert kind
        row = Alert(
            patient_id=c.patient_id, severity=severity, kind=kind,
            title=f.get("title") or "Alert", message=f.get("reason") or "",
            message_ml=None,
        )
        db.add(row)
        db.flush()
        saved_alerts.append({
            "id": row.id, "severity": row.severity, "kind": row.kind,
            "title": row.title, "message": row.message, "messageMl": None,
            "resolved": False, "createdAt": now_iso,
        })

    # Update consultation
    c.final_note = final
    c.edited_fields = edited
    c.status = "approved"
    c.document_id = doc_id

    db.flush()
    saved_alerts += after_new_data(db, c.patient_id)
    db.add(AccessLog(
        patient_id=c.patient_id, who=c.doctor_name, role="Doctor",
        action=f"{c.doctor_name} approved consultation note", via="Doctor console",
    ))
    db.commit()

    record = {
        "id": doc_id,
        "date": date_s,
        "type": "visit",
        "status": "good",
        "title": f"Visit with {c.doctor_name}",
        "provider": None,
        "doctor": c.doctor_name,
        "summary": summary,
        "observations": [{k: v[k] for k in ("name", "code", "value", "unit", "range", "status")} for v in said],
        "medications": [
            {"name": m["name"], "generic": m["generic"], "dose": m.get("dose"),
             "schedule": m.get("schedule"), "times": reminders_mod.parse_schedule(m.get("schedule")),
             "duration": m.get("duration"), "purpose": m.get("purpose")}
            for m in meds
        ],
        "followUp": follow_up,
        "source": {
            "kind": "transcript",
            "lines": [f"{ln['speaker']}: {ln['text']}" for ln in lines],
            "highlight": list(range(min(len(lines), 20))),
        },
        "isNew": True,
    }

    try:
        notify_patient(db, c.patient_id, f"{c.doctor_name} added a visit note. Open MediThread.")
    except Exception:
        pass

    return {"record": record, "alerts": saved_alerts, "reminders": rem_list}


@router.get("/{cid}")
def get_consultation(
    cid: str,
    db: Session = Depends(get_db),
    x_share_token: str | None = Header(default=None, alias="X-Share-Token"),
):
    return _consultation_out(_authorize(db, cid, x_share_token))


# ---------- scripted stage fallback ----------

DEMO_SCRIPT = [
    ("doctor",  "Hello, how are you feeling today?"),
    ("patient", "Doctor, I have been coughing for 4 days."),
    ("doctor",  "Any fever or breathlessness along with the cough?"),
    ("patient", "Yes, I feel breathless when I climb stairs for the last 3 weeks."),
    ("doctor",  "Are you taking any medicines regularly?"),
    ("patient", "I take Metformin 500 mg twice a day and Atorvastatin 10 mg at night."),
    ("doctor",  "Any known allergies to medicines or food?"),
    ("patient", "No allergies that I know of."),
    ("doctor",  "Let me listen to your chest. Breathing sounds have mild crackles."),
    ("doctor",  "I will start you on Tab Clarithromycin 500 mg BD for 7 days for the chest infection."),
    ("doctor",  "I will also add Tab Glycomet 500 mg BD to support sugar control."),
    ("patient", "Okay doctor."),
    ("doctor",  "Please come back for a follow-up review in 7 days with a repeat chest check."),
    ("patient", "Thank you, doctor."),
]


@router.post("/demo/{cid}")
def demo_feed(
    cid: str,
    db: Session = Depends(get_db),
    x_share_token: str | None = Header(default=None, alias="X-Share-Token"),
):
    c = _authorize(db, cid, x_share_token)
    if c.status == "approved":
        raise HTTPException(409, "Consultation already approved")

    last: dict = {}
    for speaker, text in DEMO_SCRIPT:
        last = add_line(cid, LineBody(speaker=speaker, text=text), db=db, x_share_token=x_share_token)
    return last
