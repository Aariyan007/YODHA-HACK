from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import store
from ..auth import current_patient
from ..database import get_db
from ..labs import lab_range, lab_status
from ..models import AccessLog, Alert, Document, Medicine, Observation, Patient
from ..schemas import access_out, alert_out, document_out, medicine_out, profile_out

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


def build_alerts(db: Session, patient_id: str) -> list[dict]:
    alerts = list(db.scalars(select(Alert).where(Alert.patient_id == patient_id)))
    alerts.sort(key=lambda a: (a.resolved, SEVERITY_ORDER.get(a.severity, 9), -a.created_at.timestamp()))
    return [alert_out(a) for a in alerts]


def build_insights(db: Session, patient: Patient) -> dict:
    obs = list(db.scalars(
        select(Observation).where(Observation.patient_id == patient.id).order_by(Observation.date)
    ))
    hba1c = [{"date": o.date, "value": o.value} for o in obs if o.code == "hba1c"]

    latest: dict[str, Observation] = {}
    for o in obs:
        latest[o.code] = o  # sorted by date, so the last one wins
    labs = [
        {"code": o.code, "name": o.name, "value": o.value, "unit": o.unit, "date": o.date,
         "status": lab_status(o.code, o.value), "range": lab_range(o.code)}
        for o in latest.values()
    ]

    summary, summary_ml = "No lab results yet.", "ഇതുവരെ ലാബ് ഫലങ്ങളൊന്നുമില്ല."
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

    return {
        "summary": summary,
        "summaryMl": summary_ml,
        "conditions": patient.conditions or [],
        "hba1c": hba1c,
        "labs": labs,
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
