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


# ---------- responses ----------

def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def profile_out(p: Patient) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "phone": p.phone,
        "age": p.age,
        "gender": p.gender,
        "bloodGroup": p.blood_group,
        "abhaId": p.abha_id,
        "language": p.language,
        "conditions": [c["name"] for c in (p.conditions or [])],
        "allergies": p.allergies or [],
    }


def document_out(d: Document) -> dict:
    items = []
    for it in d.items or []:
        it = dict(it)
        if "code" in it and "value" in it:
            it["status"] = lab_status(it["code"], it["value"])
            it["range"] = lab_range(it["code"])
        items.append(it)
    return {
        "id": d.id,
        "date": d.date,
        "type": d.type,
        "title": d.title,
        "source": d.source,
        "summary": d.summary,
        "summaryMl": d.summary_ml,
        "tags": d.tags or [],
        "items": items,
    }


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
