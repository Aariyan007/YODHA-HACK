"""Sign-in: email + password for patients and doctors (Phase 8). The old phone OTP is demo-only."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import reminder_service, store
from ..auth import create_doctor_token, create_token, current_doctor, current_patient, hash_password, require_login, verify_password
from ..database import get_db
from ..models import Patient, User, new_id
from ..schemas import NEW_PATIENT_NAME, OtpRequest, OtpVerify, profile_out, user_out

router = APIRouter(prefix="/api/auth", tags=["auth"])

OTP_TTL = 300
MAX_FAILS = 5
FAIL_WINDOW = 15 * 60
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------- helpers ----------

def _email(raw: str) -> str:
    e = (raw or "").strip().lower()
    if len(e) > 254 or not EMAIL_RE.match(e):
        raise HTTPException(400, "Please enter a valid email address.")
    return e


def _fail_key(email: str, request: Request) -> str:
    ip = request.client.host if request.client else "?"
    return f"loginfail:{email}:{ip}"


def _too_many(key: str) -> bool:
    return int(store.get_value(key) or 0) >= MAX_FAILS


def _count_fail(key: str) -> None:
    store.set_value(key, str(int(store.get_value(key) or 0) + 1), ttl=FAIL_WINDOW)


def session_for(db: Session, user: User) -> dict:
    if user.role == "doctor":
        return {"token": create_doctor_token(user.id), "profile": user_out(user)}
    patient = db.get(Patient, user.patient_id)
    return {"token": create_token(patient.id, user.id), "profile": user_out(user, patient)}


# ---------- requests ----------

class RegisterBody(BaseModel):
    role: str = Field(pattern=r"^(patient|doctor)$")
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)
    specialty: str | None = Field(default=None, max_length=80)
    hospital: str | None = Field(default=None, max_length=120)


class LoginBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)


# ---------- routes ----------

@router.get("/config")
def config():
    return {"demoLogin": reminder_service.demo_mode()}


@router.post("/register")
def register(body: RegisterBody, db: Session = Depends(get_db)):
    email = _email(body.email)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(409, "An account with this email already exists. Try signing in.")
    user = User(id=new_id(), email=email, password_hash=hash_password(body.password), role=body.role, name=body.name.strip())
    if body.role == "doctor":
        user.specialty = (body.specialty or "").strip() or None
        user.hospital = (body.hospital or "").strip() or None
    else:
        patient = Patient(name=body.name.strip(), phone=f"x-{user.id}", conditions=[], allergies=[], family=[])
        db.add(patient)
        db.flush()
        user.patient_id = patient.id
    db.add(user)
    db.commit()
    return session_for(db, user)


@router.post("/login")
def login(body: LoginBody, request: Request, db: Session = Depends(get_db)):
    email = (body.email or "").strip().lower()
    key = _fail_key(email, request)
    if _too_many(key):
        raise HTTPException(429, "Too many wrong attempts. Please wait 15 minutes and try again.")
    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(body.password, user.password_hash if user else None)
    if not (user and ok):
        _count_fail(key)
        raise HTTPException(401, "Email or password is incorrect.")
    store.delete(key)
    return session_for(db, user)


@router.get("/me")
def me(claims: dict = Depends(require_login), db: Session = Depends(get_db)):
    user = db.get(User, claims.get("uid") or "")
    if user is None:  # a demo (OTP) patient has no User row
        patient = db.get(Patient, claims.get("sub"))
        if patient is None:
            raise HTTPException(401, "Account not found")
        return {**profile_out(patient), "role": "patient"}
    patient = db.get(Patient, user.patient_id) if user.patient_id else None
    return user_out(user, patient)


# ---------- demo-only phone OTP (any 6 digits) ----------

def _require_demo() -> None:
    if not reminder_service.demo_mode():
        raise HTTPException(404, "Not found")


def _clean(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit())[-10:]


@router.post("/otp/request")
def otp_request(body: OtpRequest):
    _require_demo()
    phone = _clean(body.phone)
    store.set_value(f"otp:{phone}", "sent", ttl=OTP_TTL)
    return {"ok": True, "phone": phone, "expiresIn": OTP_TTL, "demo": True}


@router.post("/otp/verify")
def otp_verify(body: OtpVerify, db: Session = Depends(get_db)):
    _require_demo()
    phone = _clean(body.phone)
    store.delete(f"otp:{phone}")
    patient = db.scalar(select(Patient).where(Patient.phone == phone))
    if patient is None:
        patient = Patient(name=NEW_PATIENT_NAME, phone=phone, conditions=[], allergies=[], family=[])
        db.add(patient)
        db.commit()
    return {"token": create_token(patient.id), "profile": {**profile_out(patient), "role": "patient"}}
