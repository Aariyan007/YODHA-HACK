from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import store
from ..auth import create_token
from ..database import get_db
from ..models import Patient
from ..schemas import OtpRequest, OtpVerify, profile_out

router = APIRouter(prefix="/api/auth", tags=["auth"])

OTP_TTL = 300


def _clean(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits[-10:]


@router.post("/otp/request")
def otp_request(body: OtpRequest):
    phone = _clean(body.phone)
    # Demo mode: no SMS is sent. Any 6-digit code is accepted on verify.
    store.set_value(f"otp:{phone}", "sent", ttl=OTP_TTL)
    return {"ok": True, "phone": phone, "expiresIn": OTP_TTL, "demo": True}


@router.post("/otp/verify")
def otp_verify(body: OtpVerify, db: Session = Depends(get_db)):
    phone = _clean(body.phone)
    store.delete(f"otp:{phone}")
    patient = db.scalar(select(Patient).where(Patient.phone == phone))
    if patient is None:
        patient = Patient(name="New patient", phone=phone, conditions=[], allergies=[], family=[])
        db.add(patient)
        db.commit()
    return {"token": create_token(patient.id), "profile": profile_out(patient)}
