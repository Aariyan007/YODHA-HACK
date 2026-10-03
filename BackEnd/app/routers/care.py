"""Patient side of doctor access: invite codes and who can see the record."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..auth import current_patient
from ..database import get_db
from ..models import AccessLog, CareLink, InviteCode, Patient, ShareLink, User
from ..schemas import iso

router = APIRouter(prefix="/api/care", tags=["care"])

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
INVITE_HOURS = 24


def new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(8))


def pretty(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def doctor_row(link: CareLink, user: User) -> dict:
    return {"linkId": link.id, "name": user.name, "specialty": user.specialty, "hospital": user.hospital,
            "since": iso(link.created_at)}


@router.post("/invite")
def create_invite(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    """A fresh one time code. Older unused codes for this patient are removed so only one is live."""
    for old in db.scalars(select(InviteCode).where(InviteCode.patient_id == patient.id, InviteCode.used_by.is_(None))):
        db.delete(old)
    code = new_code()
    row = InviteCode(code=code, patient_id=patient.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=INVITE_HOURS))
    db.add(row)
    db.commit()
    return {"code": pretty(code), "expiresAt": iso(row.expires_at)}


@router.get("/doctors")
def my_doctors(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    links = db.scalars(select(CareLink).where(CareLink.patient_id == patient.id, CareLink.status == "active"))
    return [doctor_row(l, db.get(User, l.doctor_user_id)) for l in links]


def revoke_link(db: Session, patient: Patient, link_id: str) -> User:
    """Stops a doctor's access (the route and the agent both use it). Raises 404 if it isn't this patient's active link."""
    link = db.get(CareLink, link_id)
    if link is None or link.patient_id != patient.id or link.status != "active":
        raise HTTPException(404, "Doctor not found")
    link.status = "revoked"
    # Console links this doctor opened stop working right away (consultation calls re-check the share link).
    db.execute(delete(ShareLink).where(ShareLink.patient_id == patient.id, ShareLink.doctor_user_id == link.doctor_user_id))
    doctor = db.get(User, link.doctor_user_id)
    db.add(AccessLog(patient_id=patient.id, who=patient.name, role="Patient",
                     action=f"Removed access for {doctor.name}", via="Doctor access"))
    return doctor


@router.delete("/doctors/{link_id}")
def remove_doctor(link_id: str, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    revoke_link(db, patient, link_id)
    db.commit()
    return {"ok": True}
