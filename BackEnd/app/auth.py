import hashlib
import hmac
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .database import get_db
from .models import Patient, User

ALGORITHM = "HS256"
TOKEN_DAYS = 7
SECRET = os.getenv("JWT_SECRET") or "dev-only-secret-change-me"

bearer = HTTPBearer(auto_error=False)


# ---- passwords: stdlib scrypt, random salt, constant time compare (no extra dependency)
_N, _R, _P = 2 ** 14, 8, 1
# One scrypt run needs about 16 MB. A burst of sign-ins on 40 worker threads would need 640 MB and push a small container
# into swap and stall every other request. Only a few run at once, the rest wait their turn (milliseconds each).
_SCRYPT_SLOTS = threading.BoundedSemaphore(int(os.getenv("SCRYPT_CONCURRENCY", "3")))


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    with _SCRYPT_SLOTS:
        return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = _scrypt(password, salt, _N, _R, _P)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Always runs one scrypt, even for an unknown user (stored=None), so timing doesn't reveal which accounts exist."""
    try:
        _, n, r, p, salt, dk = (stored or _DUMMY_HASH).split("$")
        calc = _scrypt(password, bytes.fromhex(salt), int(n), int(r), int(p))
        return hmac.compare_digest(calc, bytes.fromhex(dk)) and stored is not None
    except Exception:
        return False


_DUMMY_HASH = f"scrypt${_N}${_R}${_P}${'00' * 16}${'00' * 32}"


def create_token(patient_id: str, user_id: str | None = None) -> str:
    """Patient token. `sub` stays the patient id so every /api/patients/* route works unchanged."""
    exp = datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS)
    claims = {"sub": patient_id, "role": "patient", "exp": exp}
    if user_id:
        claims["uid"] = user_id
    return jwt.encode(claims, SECRET, algorithm=ALGORITHM)


def create_doctor_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS)
    return jwt.encode({"sub": user_id, "uid": user_id, "role": "doctor", "exp": exp}, SECRET, algorithm=ALGORITHM)


def _payload(creds: HTTPAuthorizationCredentials | None) -> dict:
    if creds is None:
        raise HTTPException(401, "Missing token")
    try:
        return jwt.decode(creds.credentials, SECRET, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")


def current_patient(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Patient:
    payload = _payload(creds)
    if payload.get("role") != "patient":
        raise HTTPException(401, "This page is for patient accounts.")
    patient = db.get(Patient, payload.get("sub"))
    if patient is None:
        raise HTTPException(401, "Patient not found")
    return patient


def current_doctor(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    payload = _payload(creds)
    if payload.get("role") != "doctor":
        raise HTTPException(401, "This page is for doctor accounts.")
    user = db.get(User, payload.get("sub"))
    if user is None or user.role != "doctor":
        raise HTTPException(401, "Doctor not found")
    return user


def require_login(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    """Any valid JWT (patient or doctor)."""
    return _payload(creds)
