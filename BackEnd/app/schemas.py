"""Request bodies (pydantic) and response serializers (camelCase dicts).

Response shapes must match Frontend/src/data/mockData.js.
"""
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .labs import lab_range, lab_status
from .models import AccessLog, Alert, Document, Medicine, Patient


# ---------- requests ----------

class OtpRequest(BaseModel):
    phone: str = Field(min_length=10, max_length=15)


class OtpVerify(BaseModel):
    phone: str = Field(min_length=10, max_length=15)
    otp: str = Field(pattern=r"^\d{6}$")


class ShareCreate(BaseModel):
    hours: int = Field(default=24, ge=1, le=168)
    scope: str = Field(default="full", pattern=r"^(full|medicines|labs)$")


NEW_PATIENT_NAME = "New patient"


class ProfileUpdate(BaseModel):
    """Every field optional: only the ones sent are changed."""
    name: str | None = Field(default=None, min_length=1, max_length=120)
    age: int | None = Field(default=None, ge=0, le=120)
    gender: str | None = Field(default=None, max_length=20)
    bloodGroup: str | None = Field(default=None, max_length=5)
    language: str | None = Field(default=None, pattern=r"^(en|ml)$")
    conditions: list[str] | None = Field(default=None, max_length=30)
    allergies: list[str] | None = Field(default=None, max_length=30)
    city: str | None = Field(default=None, max_length=80)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class VitalsIn(BaseModel):
    """A reading typed in at home. At least one value is required (checked in the route)."""
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    sbp: float | None = Field(default=None, ge=50, le=300)
    dbp: float | None = Field(default=None, ge=30, le=200)
    pulse: float | None = Field(default=None, ge=20, le=250)
    spo2: float | None = Field(default=None, ge=50, le=100)
    weight: float | None = Field(default=None, ge=2, le=300)
    temp: float | None = Field(default=None, ge=90, le=110)
    sugar: float | None = Field(default=None, ge=20, le=800)
    sugarType: str = Field(default="rbs", pattern=r"^(fbs|ppbs|rbs)$")


# ---------- responses ----------

def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def profile_out(p: Patient) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "phone": p.phone if (p.phone or "").isdigit() else None,  # email sign-ups get a placeholder
        "age": p.age,
        "gender": p.gender,
        "bloodGroup": p.blood_group,
        "abhaId": p.abha_id,
        "language": p.language,
        "conditions": [c["name"] for c in (p.conditions or [])],
        "allergies": p.allergies or [],
        "city": p.city,
        "lat": p.lat,
        "lng": p.lng,
        "profileComplete": bool(p.name and p.name != NEW_PATIENT_NAME and p.age),
    }


def user_out(u, patient=None) -> dict:
    """Session profile for any login. Patients carry their patient profile; doctors a small one."""
    base = profile_out(patient) if patient is not None else {"id": u.id, "name": u.name}
    return {**base, "userId": u.id, "email": u.email, "role": u.role, "specialty": u.specialty, "hospital": u.hospital}


def document_out(d: Document) -> dict:
    items = []
    for it in d.items or []:
        it = dict(it)
        if "code" in it and "value" in it and "status" not in it:
            try:
                it["status"] = lab_status(it["code"], float(it["value"]), it.get("range"))
            except (TypeError, ValueError):
                it["status"] = "watch"
            it["range"] = it.get("range") or lab_range(it["code"])
        items.append(it)
    out = {
        "id": d.id,
        "date": d.date,
        "createdAt": iso(d.created_at) if getattr(d, "created_at", None) else None,
        "type": d.type,
        "title": d.title,
        "source": d.source,
        "summary": d.summary,
        "summaryMl": d.summary_ml,
        "tags": d.tags or [],
        "items": items,
    }
    # Phase 2 fields (only set after upload pipeline)
    for attr in ("status", "provider", "doctor", "followup"):
        v = getattr(d, attr, None)
        if v is not None:
            out[attr if attr != "followup" else "followUp"] = v
    if getattr(d, "source_kind", None) or getattr(d, "source_lines", None):
        out["sourceDoc"] = {
            "kind": d.source_kind or "image",
            "lines": d.source_lines or [],
            "highlight": d.source_highlight or [],
        }
    return out


def medicine_out(m: Medicine) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "generic": m.generic,
        "dose": m.dose,
        "frequency": m.frequency,
        "times": m.times or [],
        "instructions": m.instructions,
        "startDate": m.start_date,
        "durationDays": m.duration_days,
        "prescribedBy": m.prescribed_by,
        "active": m.active,
    }


def alert_out(a: Alert) -> dict:
    return {
        "id": a.id,
        "severity": a.severity,
        "kind": a.kind,
        "title": a.title,
        "message": a.message,
        "messageMl": a.message_ml,
        "resolved": a.resolved,
        "createdAt": iso(a.created_at),
    }


def access_out(a: AccessLog) -> dict:
    return {"id": a.id, "who": a.who, "role": a.role, "action": a.action, "via": a.via, "at": iso(a.at)}
