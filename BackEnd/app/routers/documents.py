"""Upload a document, stream the pipeline, and triage symptoms."""
from __future__ import annotations

import asyncio
import json
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ai import decision, laya_schema as S, pipeline
from ai.triage_rules import EMERGENCY_PATTERNS, emergency_hit, merge_urgency
from .. import budget
from ..auth import current_patient
from ..models import Patient

router = APIRouter(prefix="/api", tags=["documents"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# Allowed types, checked by the file's first bytes (the filename and Content-Type are only claims).
def detect_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(b"%PDF-"):
        return "pdf"
    return None


# ---------- Upload ----------

@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    patient: Patient = Depends(current_patient),
):
    budget.spend(patient.id, "upload")
    data = await file.read(MAX_UPLOAD_BYTES + 1)  # never buffer more than the limit plus one byte
    if not data:
        raise HTTPException(400, "File is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is too large (limit is 10 MB). Please take a smaller photo.")
    kind = detect_type(data)
    if kind is None:
        raise HTTPException(415, "This file type is not supported. Please upload a JPG, PNG, WEBP or PDF.")
    # Name the file by what it really is, so a renamed file cannot pick its own extension.
    job_id, from_cache = pipeline.start_job(patient.id, data, f"upload.{kind}")
    return {"jobId": job_id, "cached": from_cache}


# ---------- Jobs ----------

@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = pipeline.JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return {
        "jobId": job_id,
        "status": job["status"],
        "cached": job.get("cached", False),
        "error": job.get("error"),
        "result": job.get("result"),
    }


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str):
    """SSE stream — no auth, protected by the unguessable job_id."""
    if job_id not in pipeline.JOBS:
        raise HTTPException(404, "Job not found")

    queue = await pipeline.run_async(job_id)

    async def gen():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=60.0)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if "done" in event or "error" in event:
                break

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- Triage ----------

class TriageBody(BaseModel):
    text: str = Field(min_length=1, max_length=600)


# Keyword → specialist rules (ported from frontend symptomRules).
SYMPTOM_RULES = [
    ("chest|breath|palpit|heart", "Cardiologist", "Heart-related symptoms"),
    ("sugar|diabetes|thirst|urination|weight loss|hba1c", "Diabetologist / Endocrinologist", "Possible diabetes-related issue"),
    ("blood pressure|bp|dizzy|headache", "General Physician", "Blood-pressure or general assessment"),
    ("tooth|gum|dental", "Dentist", "Dental issue"),
    ("eye|vision|blurry|cataract", "Ophthalmologist", "Eye-related issue"),
    ("ear|hearing|dizzy|vertigo", "ENT specialist", "Ear or balance issue"),
    ("skin|rash|itch|eczema|acne", "Dermatologist", "Skin issue"),
    ("joint|knee|back pain|arthritis|muscle", "Orthopaedician", "Joint or muscle issue"),
    ("period|pregnan|menstrual|pcos", "Gynaecologist", "Women's health"),
    ("child|baby|infant|paediatric", "Paediatrician", "Child health"),
    ("anxiety|depress|sad|stress|sleep", "Psychiatrist / Psychologist", "Mental health concern"),
    ("stomach|vomit|diarrhoea|constipation|acid|gastric", "Gastroenterologist / Physician", "Digestive issue"),
    ("urine|kidney|urinary", "Nephrologist / Urologist", "Kidney or urinary issue"),
    ("fever|cold|cough|throat|flu", "General Physician", "Common infection"),
]


SPEC_CONF_MIN = 0.50  # below this the model's specialist guess is ignored and the keyword rules decide


@router.post("/triage")
def triage(body: TriageBody):
    """Which doctor, and how soon. Order: emergency keywords (rules) -> Laya (advisory, can only raise the level)
    -> specialist keyword rules -> General Physician. Never a diagnosis."""
    text = body.text.strip()
    low = text.lower()
    rule = emergency_hit(text)
    d = decision.triage(text)  # None when Laya is off, down, slow, or has not passed its quality gate
    level, src = merge_urgency("emergency" if rule else None, d["urgency"] if d else None, d["urgency_conf"] if d else 0.0)
    info = {"source": "rules", "model": None, "confidence": None}
    if d and src != "none":
        info = {"source": src, "model": d["model"], "confidence": d["urgency_conf"]}

    if level == "emergency":
        label = rule or "emergency"
        if d:
            decision.record_final("triage", text, {"level": "emergency", "by": src})
        return {"urgent": True, "specialist": "Emergency / 108",
                "why": f"Possible {label}. Call 108 immediately or go to the nearest emergency room.",
                "urgency": "emergency", **info}

    specialist, why, spec_src = None, None, "rules"
    if d and d["specialist_conf"] >= SPEC_CONF_MIN:
        specialist = S.SPECIALIST_NAME[d["specialist"]]
        why = "Covers: " + S.SPECIALISTS[d["specialist"]][1] + "."
        spec_src = "model"
    if specialist is None:
        for pattern, name, reason in SYMPTOM_RULES:
            if re.search(rf"(?<![a-z])(?:{pattern})", low):  # word start, so 'unclear' is not 'ear'
                specialist, why = name, reason
                break
    if specialist is None:
        specialist, why = "General Physician", "A general check-up is a good starting point."
    if level == "urgent":
        why = "Please see a doctor within a day. " + why
    if d:
        decision.record_final("triage", text, {"level": level, "specialist": specialist, "specialist_by": spec_src})
    return {"urgent": False, "specialist": specialist, "why": why, "urgency": level, "soon": level == "urgent",
            "specialistSource": spec_src, **info}
