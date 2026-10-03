import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from .. import store
from ..auth import current_patient
from ..database import get_db
from ai import health_review

from ..health_hooks import after_new_data
from ..labs import lab_name, lab_range, lab_status, loinc_for
from ..risk import assess
from ..vitals import obs as vitals_obs
from ..models import AccessLog, Alert, Document, Medicine, Observation, Patient
from ..schemas import ProfileUpdate, VitalsIn, access_out, alert_out, document_out, medicine_out, profile_out

router = APIRouter(prefix="/api/patients/me", tags=["patient"])

IST = ZoneInfo("Asia/Kolkata")
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def today() -> str:
    return datetime.now(IST).date().isoformat()


# ---------- shared builders (also used by shares router) ----------

def build_timeline(db: Session, patient_id: str) -> list[dict]:
    docs = db.scalars(
        select(Document).where(Document.patient_id == patient_id).order_by(Document.date.desc(), Document.created_at.desc())
    )
    return [document_out(d) for d in docs]


def build_medicines(db: Session, patient_id: str) -> list[dict]:
    meds = db.scalars(select(Medicine).where(Medicine.patient_id == patient_id, Medicine.active.is_(True)))
    return [medicine_out(m) for m in meds]


# Alert kinds that are a note to the PATIENT about their own upload (e.g. "I could not read this handwriting, check it with your
# pharmacist"). A doctor, a share link or a PDF handed to a doctor must never carry them.
PATIENT_ONLY_KINDS = ("handwriting",)


def build_alerts(db: Session, patient_id: str, for_doctor: bool = False) -> list[dict]:
    q = select(Alert).where(Alert.patient_id == patient_id)
    if for_doctor:
        q = q.where(Alert.kind.not_in(PATIENT_ONLY_KINDS))
    alerts = list(db.scalars(q))
    alerts.sort(key=lambda a: (a.resolved, SEVERITY_ORDER.get(a.severity, 9), -a.created_at.timestamp()))
    return [alert_out(a) for a in alerts]


def build_insights(db: Session, patient: Patient) -> dict:
    obs = list(db.scalars(
        select(Observation).where(Observation.patient_id == patient.id).order_by(Observation.date)
    ))
    hba1c = [{"date": o.date, "value": o.value} for o in obs if o.code == "hba1c"]

    latest: dict[str, Observation] = {}
    series: dict[str, dict] = {}
    for o in obs:
        latest[o.code] = o  # sorted by date, so the last one wins
        s = series.setdefault(o.code, {"code": o.code, "name": lab_name(o.code, o.name), "unit": o.unit,
                                       "range": lab_range(o.code) or o.ref_range, "points": []})
        s["points"].append({"date": o.date, "value": o.value})
    labs = [
        {"code": o.code, "name": lab_name(o.code, o.name), "value": o.value, "unit": o.unit, "date": o.date,
         "status": lab_status(o.code, o.value, o.ref_range), "range": lab_range(o.code) or o.ref_range}
        for o in latest.values()
    ]
    labs.sort(key=lambda l: l["date"], reverse=True)

    summary, summary_ml = ("No results yet. Add a report or a home reading to start your health thread.",
                           "ഇതുവരെ ഫലങ്ങളൊന്നുമില്ല. ഒരു റിപ്പോർട്ടോ വീട്ടിലെ റീഡിംഗോ ചേർക്കുക.")
    if len(hba1c) >= 2:
        first, last = hba1c[0]["value"], hba1c[-1]["value"]
        if last < first:
            summary = f"Your sugar average (HbA1c) improved from {first}% to {last}%. Keep going."
            summary_ml = f"നിങ്ങളുടെ പഞ്ചസാര ശരാശരി (HbA1c) {first}%-ൽ നിന്ന് {last}% ആയി മെച്ചപ്പെട്ടു. തുടരുക."
        else:
            summary = f"Your sugar average (HbA1c) went from {first}% to {last}%. Talk to your doctor."
            summary_ml = f"നിങ്ങളുടെ പഞ്ചസാര ശരാശരി (HbA1c) {first}%-ൽ നിന്ന് {last}% ആയി. ഡോക്ടറോട് സംസാരിക്കുക."
    elif hba1c:
        summary = f"Your last sugar average (HbA1c) was {hba1c[-1]['value']}%."
        summary_ml = f"നിങ്ങളുടെ അവസാന പഞ്ചസാര ശരാശരി (HbA1c) {hba1c[-1]['value']}% ആയിരുന്നു."
    elif labs:
        off = [l for l in labs if l["status"] != "good"]
        if off:
            names = ", ".join(l["name"] for l in off[:3])
            summary = f"{len(off)} of your {len(labs)} latest results need a look: {names}. Show them to your doctor."
            summary_ml = f"നിങ്ങളുടെ {len(labs)} പുതിയ ഫലങ്ങളിൽ {len(off)} എണ്ണം ശ്രദ്ധിക്കണം: {names}. ഡോക്ടറെ കാണിക്കുക."
        else:
            summary = f"Your {len(labs)} latest results are in the usual range."
            summary_ml = f"നിങ്ങളുടെ {len(labs)} പുതിയ ഫലങ്ങളും സാധാരണ പരിധിയിലാണ്."

    return {
        "summary": summary,
        "summaryMl": summary_ml,
        "conditions": patient.conditions or [],
        "hba1c": hba1c,
        "labs": labs,
        # Every test with 2+ results, for charts (newest test first).
        "series": sorted((s for s in series.values() if len(s["points"]) >= 2),
                         key=lambda s: s["points"][-1]["date"], reverse=True),
    }


def build_reminders(db: Session, patient_id: str, date: str) -> list[dict]:
    out = []
    for m in db.scalars(select(Medicine).where(Medicine.patient_id == patient_id, Medicine.active.is_(True))):
        for t in m.times or []:
            key = f"{m.id}_{t.replace(':', '')}"
            out.append({
                "key": key,
                "medicineId": m.id,
                "name": m.name,
                "dose": m.dose,
                "instructions": m.instructions,
                "time": t,
                "date": date,
                "taken": store.get_value(f"taken:{patient_id}:{date}:{key}") is not None,
            })
    out.sort(key=lambda r: r["time"])
    return out


# ---------- routes ----------

@router.get("")
def me(patient: Patient = Depends(current_patient)):
    return profile_out(patient)


@router.get("/timeline")
def timeline(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    return build_timeline(db, patient.id)


@router.get("/alerts")
def alerts(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    return build_alerts(db, patient.id)


@router.get("/insights")
def insights(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    return build_insights(db, patient)


@router.get("/medicines")
def medicines(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    return build_medicines(db, patient.id)


@router.get("/reminders")
def reminders(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    return build_reminders(db, patient.id, today())


@router.post("/reminders/{key}/taken")
def reminder_taken(key: str, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    date = today()
    keys = {r["key"] for r in build_reminders(db, patient.id, date)}
    if key not in keys:
        raise HTTPException(404, "Reminder not found")
    from .. import reminder_service
    reminder_service.mark_taken(db, patient.id, key, date)
    return {"key": key, "date": date, "taken": True}


@router.get("/access-log")
def access_log(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    rows = db.scalars(select(AccessLog).where(AccessLog.patient_id == patient.id).order_by(AccessLog.at.desc()))
    return [access_out(a) for a in rows]


@router.get("/family")
def family(patient: Patient = Depends(current_patient)):
    return patient.family or []


@router.put("")
def update_me(body: ProfileUpdate, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    """Edit the profile. Only the fields sent are changed."""
    data = body.model_dump(exclude_unset=True)
    clean = lambda xs: [x.strip()[:80] for x in xs if x and x.strip()]  # noqa: E731
    if "name" in data:
        patient.name = data["name"].strip()
    for field, attr in (("age", "age"), ("gender", "gender"), ("bloodGroup", "blood_group"), ("language", "language"),
                        ("lat", "lat"), ("lng", "lng")):
        if field in data:
            setattr(patient, attr, data[field])
    if "city" in data:
        patient.city = (data["city"] or "").strip() or None
    if "allergies" in data:
        patient.allergies = clean(data["allergies"] or [])
    if "conditions" in data:
        old = {c["name"].lower(): c for c in (patient.conditions or [])}
        patient.conditions = [old.get(n.lower(), {"name": n}) for n in clean(data["conditions"] or [])]
    db.commit()
    return profile_out(patient)


@router.post("/vitals")
def add_vitals(body: VitalsIn, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    """A reading typed at home: BP, pulse, oxygen, weight, temperature, sugar. Runs the danger checks."""
    values = []
    if (body.sbp is None) != (body.dbp is None):
        raise HTTPException(422, "Enter both blood pressure numbers (top and bottom).")
    if body.sbp is not None and body.sbp <= body.dbp:
        raise HTTPException(422, "The top blood pressure number must be bigger than the bottom one.")
    for code in ("sbp", "dbp", "pulse", "spo2", "weight", "temp"):
        v = getattr(body, code)
        if v is not None:
            values.append(vitals_obs(code, float(v)))
    if body.sugar is not None:
        values.append(vitals_obs(body.sugarType, float(body.sugar)))
    if not values:
        raise HTTPException(422, "Enter at least one reading.")

    date_s = body.date or today()
    for v in values:
        v["status"] = lab_status(v["code"], v["value"])
        v["range"] = lab_range(v["code"])
    bp = next((v for v in values if v["code"] == "sbp"), None)
    title = "Home reading" + (f": BP {values[0]['value']:g}/{values[1]['value']:g}" if bp else "")
    doc = Document(patient_id=patient.id, date=date_s, type="vitals", title=title, source="Home reading",
                   summary="Reading added at home: " + ", ".join(f"{v['name']} {v['value']:g} {v['unit']}" for v in values) + ".",
                   summary_ml="വീട്ടിൽ എടുത്ത റീഡിംഗ്: " + ", ".join(f"{v['name']} {v['value']:g} {v['unit']}" for v in values) + ".",
                   items=[{k: v[k] for k in ("name", "code", "value", "unit", "range", "status")} for v in values],
                   status=max((v["status"] for v in values), key=["good", "watch", "alert"].index), origin="home")
    db.add(doc)
    db.flush()
    for v in values:
        db.add(Observation(patient_id=patient.id, document_id=doc.id, date=date_s, code=v["code"], name=v["name"],
                           value=v["value"], unit=v["unit"], loinc=loinc_for(v["code"]), source="home"))
    db.flush()
    after_new_data(db, patient.id)
    db.add(AccessLog(patient_id=patient.id, who=patient.name, role="Patient", action="Added a home reading", via="App"))
    db.commit()
    return {"record": document_out(doc), "risks": assess(db, patient.id), "alerts": build_alerts(db, patient.id)}


@router.get("/health-check")
def health_check(ai: bool = True, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    """Danger checks (Python) + an AI review of the whole record. The AI never changes a risk level."""
    if not ai:
        return build_health_check(db, patient, use_ai=False)
    from .. import budget
    # The AI review is the slow, quota-limited part. Reuse it for 2 minutes, but only while the record is unchanged.
    key = f"hc:{patient.id}:{_record_fingerprint(db, patient.id)}"
    hit = store.get_value(key)
    if hit:
        try:
            return json.loads(hit)
        except ValueError:
            pass
    if not budget.try_spend(patient.id, "review"):  # over today's AI budget: the rules-only review still works
        return build_health_check(db, patient, use_ai=False)
    out = build_health_check(db, patient, use_ai=True)
    if (out.get("review") or {}).get("source") != "rules":  # do not keep a fallback answer from a moment when the AI was down
        store.set_value(key, json.dumps(out), ttl=120)
    return out


def _record_fingerprint(db: Session, pid: str) -> str:
    """Changes whenever the record does: counts and newest ids of everything the review reads."""
    from sqlalchemy import func
    parts = []
    for model, extra in ((Document, None), (Observation, None), (Medicine, None), (Alert, Alert.resolved)):
        q = select(func.count(), func.max(model.id)).where(model.patient_id == pid)
        if extra is not None:
            q = select(func.count(), func.max(model.id), func.sum(case((extra.is_(True), 1), else_=0))).where(model.patient_id == pid)
        parts.append("-".join(str(x) for x in db.execute(q).one()))
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def build_health_check(db: Session, patient: Patient, use_ai: bool = True, for_doctor: bool = False) -> dict:
    risks = assess(db, patient.id)
    ins = build_insights(db, patient)
    meds = build_medicines(db, patient.id)
    alerts = build_alerts(db, patient.id, for_doctor=for_doctor)
    # Single-reading tests still help the AI ("only one BP reading"), so pass every test.
    obs_series = {s["code"]: s for s in ins["series"]}
    for l in ins["labs"]:
        obs_series.setdefault(l["code"], {"code": l["code"], "name": l["name"], "unit": l["unit"], "range": l["range"],
                                          "points": [{"date": l["date"], "value": l["value"]}]})
    rev = health_review.review(profile_out(patient), list(obs_series.values()), meds, alerts, risks, use_ai=use_ai)
    top = risks[0] if risks else None
    return {
        "risks": risks,
        "review": rev,
        "emergency": bool(top and top["emergency"]),
        "specialist": top["specialist"] if top else None,
        "reason": top["reason"] if top else None,
        "checkedAt": datetime.now(IST).isoformat(),
    }
