"""Delete throwaway accounts and everything they own.

    cd BackEnd && ./venv/bin/python scripts/cleanup_test_accounts.py                 # smoke-* and sweep-* accounts
    cd BackEnd && ./venv/bin/python scripts/cleanup_test_accounts.py a@x.com b@y.com # those exact emails too

smoke.py and security_sweep.py call this at the end, so they leave nothing behind.
Never touches the seeded demo patient (no User row).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, or_, select

from app.database import SessionLocal
from app.models import (AccessLog, Alert, CareLink, Consultation, Document, InviteCode, Medicine, Observation, Patient,
                        ReminderSettings, SentDose, SentNotice, ShareLink, User)

PREFIXES = ("smoke-", "sweep-")


def cleanup(extra_emails: tuple[str, ...] = ()) -> int:
    with SessionLocal() as db:
        cond = [User.email.like(f"{p}%@example.com") for p in PREFIXES] + ([User.email.in_([e.lower() for e in extra_emails])] if extra_emails else [])
        users = list(db.scalars(select(User).where(or_(*cond))))
        uids = [u.id for u in users]
        pids = [u.patient_id for u in users if u.patient_id]
        if not users:
            return 0
        db.execute(delete(CareLink).where(or_(CareLink.doctor_user_id.in_(uids), CareLink.patient_id.in_(pids))))
        db.execute(delete(ShareLink).where(or_(ShareLink.doctor_user_id.in_(uids), ShareLink.patient_id.in_(pids))))
        db.execute(delete(InviteCode).where(InviteCode.patient_id.in_(pids)))
        for model in (SentDose, SentNotice, Consultation, Observation, Medicine, Alert, AccessLog, Document, ReminderSettings):
            col = model.patient_id
            db.execute(delete(model).where(col.in_(pids)))
        db.execute(delete(User).where(User.id.in_(uids)))
        db.execute(delete(Patient).where(Patient.id.in_(pids)))
        db.commit()
        return len(users)


if __name__ == "__main__":
    print(f"removed {cleanup(tuple(sys.argv[1:]))} account(s)")
