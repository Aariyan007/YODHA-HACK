"""Doctor finder: nearby doctors on an India map, ranked in Python, explained by AI.

All doctors are FICTIONAL sample data (BackEnd/data/doctors.json).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai import doctor_ai

from .. import doctors as finder
from ..auth import current_patient
from ..database import get_db
from ..models import Medicine, Observation, Patient
from ..risk import EMERGENCY, assess

router = APIRouter(prefix="/api/doctors", tags=["doctors"])

DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun", "today"}


def _lang(p: Patient) -> str:
    return "Malayalam" if (p.language or "en") == "ml" else "English"


def _out(origin: dict, found: dict, picks: list[dict], **extra) -> dict:
    return {
        "origin": origin,
        "specialty": found["specialty"],
        "results": found["results"],
        "picks": picks,
        "relaxed": found["relaxed"],
        "nearbyGp": found.get("nearbyGp", []),
        "bounds": finder.INDIA_BOUNDS,
        "sample": True,
        **extra,
    }


@router.get("/cities")
def cities():
    return finder.cities()


@router.get("/nearby")
def nearby(
    lat: float | None = None, lng: float | None = None, city: str | None = None,
    specialty: str | None = None, language: str | None = None, day: str | None = None,
    openNow: bool = False, emergency: bool = False, teleconsult: bool = False,
    maxKm: float | None = Query(default=None, gt=0, le=3000), maxFee: int | None = Query(default=None, ge=0),
    minRating: float | None = Query(default=None, ge=1, le=5), limit: int = Query(default=12, ge=1, le=40),
    ai: bool = True,
    patient: Patient = Depends(current_patient),
):
    origin = finder.resolve_origin(lat, lng, city, patient.lat, patient.lng, patient.city)
    spec = specialty if specialty in finder.SPECIALTIES else None
    found = finder.search(origin, spec, language if language in finder.LANGUAGES else None,
                          day if day in DAYS else None, openNow, emergency, maxKm, maxFee, minRating, teleconsult, limit)
    ctx = {"need": spec or "any doctor", "language": language or _lang(patient), "age": patient.age}
    picks = doctor_ai.explain(found["results"], ctx) if ai else []
    return _out(origin, found, picks)


class AskBody(BaseModel):
    q: str = Field(min_length=2, max_length=300)
    lat: float | None = None
    lng: float | None = None


@router.post("/ask")
def ask(body: AskBody, patient: Patient = Depends(current_patient)):
    """Free-text search: Python reads what it can, the AI fills the rest (only known values)."""
    rules = finder.parse_query(body.q)
    ai_filters = doctor_ai.parse(body.q)
    filters = {**ai_filters, **rules}  # a Python match is exact, so it wins over the AI's guess
    source = "ai+rules" if ai_filters and rules else ("ai" if ai_filters else "rules")
    origin = finder.resolve_origin(body.lat, body.lng, filters.get("city"), patient.lat, patient.lng, patient.city)
    if filters.get("city"):
        # A town named in the question beats the device location.
        c = finder.city_coords(filters["city"])
        origin = {"lat": c["lat"], "lng": c["lng"], "label": c["city"], "source": "question", "outsideIndia": False}
    found = finder.search(origin, filters.get("specialty"), filters.get("language"), filters.get("day"),
                          bool(filters.get("openNow")), bool(filters.get("emergency")), filters.get("maxKm"),
                          filters.get("maxFee"), filters.get("minRating"), bool(filters.get("teleconsult")))
    ctx = {"need": body.q, "language": filters.get("language") or _lang(patient), "age": patient.age}
    picks = doctor_ai.explain(found["results"], ctx)
    return _out(origin, found, picks, filters=filters, filtersSource=source, query=body.q)


def _bring_list(db: Session, patient: Patient, risk: dict | None) -> list[dict]:
    """What to take to the doctor, built from the patient's own record (no AI)."""
    out: list[dict] = []
    codes = {e["code"] for e in (risk or {}).get("evidence", [])}
    if codes & {"sbp", "dbp"}:
        codes |= {"sbp", "dbp"}
    if codes:
        rows = list(db.scalars(select(Observation).where(Observation.patient_id == patient.id,
                                                          Observation.code.in_(codes)).order_by(Observation.date)))
        if {"sbp", "dbp"} <= codes:
            by_date: dict[str, dict] = {}
            for o in rows:
                by_date.setdefault(o.date, {})[o.code] = o.value
            bp = [f"{v['sbp']:g}/{v['dbp']:g} ({d})" for d, v in sorted(by_date.items()) if "sbp" in v and "dbp" in v][-3:]
            if bp:
                out.append({"text": "Your last blood pressure readings: " + ", ".join(bp),
                            "textMl": "നിങ്ങളുടെ അവസാന ബിപി റീഡിംഗുകൾ: " + ", ".join(bp)})
        for code in codes - {"sbp", "dbp"}:
            vals = [o for o in rows if o.code == code][-3:]
            if vals:
                txt = ", ".join(f"{o.value:g} ({o.date})" for o in vals)
                out.append({"text": f"Your last {vals[-1].name} results: {txt}", "textMl": f"{vals[-1].name}: {txt}"})
    meds = [m.name for m in db.scalars(select(Medicine).where(Medicine.patient_id == patient.id, Medicine.active.is_(True)))]
    if meds:
        out.append({"text": "Your medicine list: " + ", ".join(meds), "textMl": "നിങ്ങളുടെ മരുന്നുകൾ: " + ", ".join(meds)})
    if patient.allergies:
        out.append({"text": "Allergies: " + ", ".join(patient.allergies), "textMl": "അലർജി: " + ", ".join(patient.allergies)})
    out.append({"text": "Your MediThread share QR (Sharing tab), so the doctor can see every report",
                "textMl": "MediThread ഷെയർ QR (Sharing ടാബ്), ഡോക്ടർക്ക് എല്ലാ റിപ്പോർട്ടുകളും കാണാൻ"})
    return out


@router.get("/recommend")
def recommend(lat: float | None = None, lng: float | None = None, city: str | None = None,
              patient: Patient = Depends(current_patient), db: Session = Depends(get_db)):
    """Doctors for the most serious thing in the patient's record (from app/risk.py)."""
    risks = assess(db, patient.id)
    top = risks[0] if risks else None
    origin = finder.resolve_origin(lat, lng, city, patient.lat, patient.lng, patient.city)
    emergency = bool(top and top["emergency"])
    specialty = EMERGENCY if emergency else (top["specialist"] if top else "General Physician")
    found = finder.search(origin, specialty, None, None, False, emergency, None, None, None, False, 10)
    ctx = {"need": top["title"] if top else "a routine check-up", "language": _lang(patient), "age": patient.age}
    picks = doctor_ai.explain(found["results"], ctx)
    return _out(origin, found, picks, risk=top, risks=risks, emergency=emergency, bring=_bring_list(db, patient, top))
