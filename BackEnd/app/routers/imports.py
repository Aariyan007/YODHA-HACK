"""Hospital record import (Phase 6): POST /api/import/fhir."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from ..auth import current_patient
from ..fhir_import import MAX_BYTES, FhirImportError, import_bundle
from ..models import Patient

router = APIRouter(prefix="/api/import", tags=["import"])

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "aster_medcity_bundle.json"


@router.get("/fhir/sample")
def fhir_sample(patient: Patient = Depends(current_patient)):
    """The fictional hospital bundle, so the app can offer 'Use sample hospital record'."""
    return json.loads(SAMPLE.read_text())


@router.post("/fhir")
async def import_fhir(request: Request, patient: Patient = Depends(current_patient)):
    """Body is the Bundle JSON itself, or a multipart form with a `file` field. Max 2 MB."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES + 4096:
        raise HTTPException(413, "This file is bigger than 2 MB. Please send a smaller hospital export.")
    if request.headers.get("content-type", "").startswith("multipart/"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(400, "Please choose a hospital record file (.json).")
        raw = await upload.read()
    else:
        raw = await request.body()
    if not raw:
        raise HTTPException(400, "The file is empty.")
    try:
        return await run_in_threadpool(import_bundle, patient.id, raw)
    except FhirImportError as e:
        raise HTTPException(e.status, str(e))
