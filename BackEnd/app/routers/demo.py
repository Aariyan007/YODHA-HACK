"""Demo-mode endpoints (Phase 6). Every route is a 404 unless DEMO_MODE=true."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from .. import demo, reminder_service as svc
from ..auth import current_patient
from ..models import Patient

router = APIRouter(prefix="/api", tags=["demo"])


def _require_demo() -> None:
    if not svc.demo_mode():
        raise HTTPException(404, "Not found")


@router.post("/demo/reset")
async def demo_reset(patient: Patient = Depends(current_patient)):
    _require_demo()
    return await run_in_threadpool(demo.reset_demo)


@router.get("/health/deep")
async def health_deep(patient: Patient = Depends(current_patient)):
    _require_demo()
    return await run_in_threadpool(demo.deep_health)
