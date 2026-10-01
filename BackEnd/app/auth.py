import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .database import get_db
from .models import Patient

ALGORITHM = "HS256"
TOKEN_DAYS = 7
SECRET = os.getenv("JWT_SECRET") or "dev-only-secret-change-me"

bearer = HTTPBearer(auto_error=False)


def create_token(patient_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS)
    return jwt.encode({"sub": patient_id, "role": "patient", "exp": exp}, SECRET, algorithm=ALGORITHM)


def current_patient(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Patient:
    if creds is None:
        raise HTTPException(401, "Missing token")
    try:
        payload = jwt.decode(creds.credentials, SECRET, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")
    patient = db.get(Patient, payload.get("sub"))
    if patient is None:
        raise HTTPException(401, "Patient not found")
    return patient
