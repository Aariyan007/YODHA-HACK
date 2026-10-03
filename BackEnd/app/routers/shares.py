import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import current_patient
from ..database import get_db
from ..models import AccessLog, Patient, ShareLink
from ..schemas import ShareCreate, iso, profile_out
from ..risk import assess
from .patients import build_alerts, build_insights, build_medicines, build_timeline

router = APIRouter(prefix="/api/shares", tags=["shares"])


def make_share(db: Session, patient_id: str, scope: str, hours: int) -> ShareLink:
    """The one place a share link is made (the route and the agent both use it). Does not commit."""
    link = ShareLink(token=secrets.token_urlsafe(16), patient_id=patient_id, scope=scope,
                     expires_at=datetime.now(timezone.utc) + timedelta(hours=hours))
    db.add(link)
    db.flush()
    return link


@router.post("")
def create_share(body: ShareCreate, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    link = make_share(db, patient.id, body.scope, body.hours)
    db.commit()
    return {"token": link.token, "url": f"/share/{link.token}", "scope": link.scope, "expiresAt": iso(link.expires_at)}


@router.get("/{token}/snapshot")
def snapshot(token: str, viewer: str = "Share link viewer", db: Session = Depends(get_db)):
    link = db.get(ShareLink, token)
    if link is None:
        raise HTTPException(404, "Share link not found")
    expires = link.expires_at if link.expires_at.tzinfo else link.expires_at.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(410, "Share link expired")

    patient = db.get(Patient, link.patient_id)
    db.add(AccessLog(patient_id=patient.id, who=viewer[:120], role="Viewer",
                     action=f"Viewed {link.scope} snapshot", via="Share link"))
    db.commit()

    timeline = build_timeline(db, patient.id)
    if link.scope == "labs":
        timeline = [d for d in timeline if d["type"] == "lab"]
    elif link.scope == "medicines":
        timeline = [d for d in timeline if d["type"] == "prescription"]
    return {
        "patient": profile_out(patient),
        "scope": link.scope,
        "expiresAt": iso(expires),
        "timeline": timeline,
        "medicines": build_medicines(db, patient.id),
        "alerts": build_alerts(db, patient.id, for_doctor=True),
        "insights": build_insights(db, patient) if link.scope != "medicines" else None,
        "risks": assess(db, patient.id) if link.scope != "medicines" else [],
    }
