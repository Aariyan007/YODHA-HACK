"""Upload a document, stream the pipeline, and triage symptoms."""
from __future__ import annotations

import asyncio
import json
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ai import pipeline
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


EMERGENCY_PATTERNS = [
    (r"\bchest\s+pain\b|\bheart\s+attack\b", "chest pain"),
    (r"\bcan'?t\s+breathe\b|\bshort(ness)?\s+of\s+breath\b|\bbreathless\b", "trouble breathing"),
    (r"\bface\s+droop(ing)?\b|\bslurred\s+speech\b|\bweak(ness)?\s+(on\s+)?one\s+side\b|\bstroke\b", "signs of stroke"),
    (r"\bfaint(ing|ed)?\b|\bunconscious\b|\bpassed\s+out\b", "fainting"),
    (r"\bbleeding\s+heavily\b|\buncontroll(ed|able)\s+bleeding\b", "heavy bleeding"),
    (r"\bsevere\s+allergic\b|\banaphylaxis\b|\bswollen\s+tongue\b", "severe allergy"),
]

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


@router.post("/triage")
def triage(body: TriageBody):
    text = body.text.strip().lower()

    # Emergency keywords first — pure Python, no AI.
    for pattern, label in EMERGENCY_PATTERNS:
        if re.search(pattern, text):
            return {
                "urgent": True,
                "specialist": "Emergency / 108",
                "why": f"Possible {label}. Call 108 immediately or go to the nearest emergency room.",
            }

    # Deterministic rules first (match on keywords in the frontend symptomRules).
    for pattern, specialist, why in SYMPTOM_RULES:
        if re.search(pattern, text):
            return {"urgent": False, "specialist": specialist, "why": why}

    # Fallback: ask Groq for a specialist TYPE only (never a disease).
    try:
        from groq import Groq
        import os
        client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=15.0)
        r = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content":
                 "You help a lay patient decide which TYPE of doctor to see. "
                 "Reply ONLY as a single JSON object with keys 'specialist' and 'why'. "
                 "'specialist' is a doctor type (General Physician, Cardiologist, Dermatologist, …). "
                 "'why' is one short reason, no diagnosis. Default to 'General Physician' if unsure."},
                {"role": "user", "content": body.text[:500]},
            ],
            max_tokens=120, temperature=0.2,
            response_format={"type": "json_object"},
        )
        data = json.loads(r.choices[0].message.content or "{}")
        return {
            "urgent": False,
            "specialist": data.get("specialist") or "General Physician",
            "why": data.get("why") or "A general check-up is a good starting point.",
        }
    except Exception as e:
        print(f"[triage] fallback failed: {type(e).__name__}")
        return {"urgent": False, "specialist": "General Physician", "why": "A general check-up is a good starting point."}
