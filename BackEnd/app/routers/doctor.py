"""Doctor side: link a patient with their invite code, list patients, open a record, start a consultation.

Every patient route first checks for an ACTIVE CareLink and answers 404 otherwise, so a doctor can't tell
whether a patient id exists.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import store
from ..auth import current_doctor
from ..database import get_db
from ..models import AccessLog, Alert, CareLink, Document, InviteCode, Patient, ShareLink, User
from ..risk import assess
from ..schemas import iso, profile_out
from .patients import build_alerts, build_insights, build_medicines, build_timeline

router = APIRouter(prefix="/api/doctor", tags=["doctor"])

CONSOLE_HOURS = 8
MAX_BAD_CODES = 10
BAD_CODE_WINDOW = 15 * 60


class LinkBody(BaseModel):
    code: str = Field(min_length=4, max_length=20)


def _linked_patient(db: Session, doctor: User, patient_id: str) -> Patient:
    link = db.scalar(select(CareLink).where(CareLink.patient_id == patient_id, CareLink.doctor_user_id == doctor.id,
                                            CareLink.status == "active"))
    patient = db.get(Patient, patient_id) if link else None
    if patient is None:
        raise HTTPException(404, "Patient not found")
    return patient


def _log(db: Session, doctor: User, patient: Patient, action: str) -> None:
    db.add(AccessLog(patient_id=patient.id, who=doctor.name, role="Doctor", action=action, via="Doctor account"))


@router.post("/link")
def link_patient(body: LinkBody, doctor: User = Depends(current_doctor), db: Session = Depends(get_db)):
    key = f"badcode:{doctor.id}"
    if int(store.get_value(key) or 0) >= MAX_BAD_CODES:
        raise HTTPException(429, "Too many wrong codes. Please wait 15 minutes and try again.")
    code = "".join(ch for ch in body.code.upper() if ch.isalnum())
    invite = db.get(InviteCode, code)
    now = datetime.now(timezone.utc)
    if invite is not None:
        exp = invite.expires_at if invite.expires_at.tzinfo else invite.expires_at.replace(tzinfo=timezone.utc)
    if invite is None or invite.used_by is not None or exp < now:
        store.set_value(key, str(int(store.get_value(key) or 0) + 1), ttl=BAD_CODE_WINDOW)
        raise HTTPException(400, "That code is not valid. Ask the patient for a new one (codes work once and expire after 24 hours).")
    invite.used_by = doctor.id
    link = db.scalar(select(CareLink).where(CareLink.patient_id == invite.patient_id, CareLink.doctor_user_id == doctor.id))
    if link is None:
        link = CareLink(patient_id=invite.patient_id, doctor_user_id=doctor.id)
        db.add(link)
    link.status = "active"
    patient = db.get(Patient, invite.patient_id)
    _log(db, doctor, patient, "Added as the patient's doctor")
    db.commit()
    return {"patientId": patient.id, "name": patient.name}


@router.get("/patients")
def my_patients(doctor: User = Depends(current_doctor), db: Session = Depends(get_db)):
    out = []
    for link in db.scalars(select(CareLink).where(CareLink.doctor_user_id == doctor.id, CareLink.status == "active")):
        p = db.get(Patient, link.patient_id)
        open_alerts = db.scalar(select(func.count()).select_from(Alert).where(Alert.patient_id == p.id, Alert.resolved.is_(False))) or 0
        last = db.scalar(select(func.max(Document.date)).where(Document.patient_id == p.id))
        out.append({"patientId": p.id, "name": p.name, "age": p.age, "gender": p.gender, "openAlerts": open_alerts,
                    "lastRecord": last, "since": iso(link.created_at)})
    out.sort(key=lambda r: r["name"].lower())
    return out


@router.get("/patients/{patient_id}/snapshot")
def patient_snapshot(patient_id: str, doctor: User = Depends(current_doctor), db: Session = Depends(get_db)):
    """Same shape as the share snapshot, so the existing read-only record view can show it."""
    patient = _linked_patient(db, doctor, patient_id)
    _log(db, doctor, patient, "Viewed full history")
    db.commit()
    return {
        "patient": profile_out(patient), "scope": "full", "expiresAt": None,
        "timeline": build_timeline(db, patient.id), "medicines": build_medicines(db, patient.id),
        "alerts": build_alerts(db, patient.id, for_doctor=True), "insights": build_insights(db, patient), "risks": assess(db, patient.id),
    }


@router.post("/patients/{patient_id}/console-token")
def console_token(patient_id: str, doctor: User = Depends(current_doctor), db: Session = Depends(get_db)):
    """A normal share link (8 h), so the existing consultation console and its X-Share-Token flow get reused."""
    patient = _linked_patient(db, doctor, patient_id)
    link = ShareLink(token=secrets.token_urlsafe(16), patient_id=patient.id, scope="full", doctor_user_id=doctor.id,
                     expires_at=datetime.now(timezone.utc) + timedelta(hours=CONSOLE_HOURS))
    db.add(link)
    _log(db, doctor, patient, "Opened the consultation console")
    db.commit()
    return {"token": link.token, "doctorName": doctor.name, "expiresAt": iso(link.expires_at)}
