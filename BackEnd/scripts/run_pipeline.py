"""Runs the full upload pipeline on each test image and prints a report."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai import pipeline  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.seed import seed_if_empty  # noqa: E402

DEMO_PATIENT_ID = "ammini01"


def _fresh_db():
    """Drop every table and re-seed so each run starts clean."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_if_empty(db)
DOCS = [
    "sunrise_prescription.png",
    "lab_report.png",
    "blurry_photo.png",
]


async def _run(name: str):
    path = ROOT / "test_docs" / name
    data = path.read_bytes()
    print(f"\n=========================\n   {name}  ({len(data)/1024:.1f} KB)\n=========================")
    t0 = time.monotonic()
    job_id, _ = pipeline.start_job(DEMO_PATIENT_ID, data, name)
    queue = await pipeline.run_async(job_id)
    stages: list[str] = []
    final = None
    while True:
        event = await asyncio.wait_for(queue.get(), timeout=90.0)
        if "stage" in event:
            stages.append(event["stage"])
        else:
            final = event
            break
    dt = time.monotonic() - t0

    print(f"stages:  {' -> '.join(stages)}")
    print(f"time:    {dt:.1f}s")
    if "error" in final:
        print(f"ERROR:   {final['error']}")
        return

    res = final["result"]
    rec = res["record"]
    print(f"record:  {rec['type']} {rec['date']} — {rec['title']}  (status={rec['status']})")
    print(f"doctor:  {rec['doctor']} @ {rec['provider']}")
    print(f"summary EN: {rec['summary']['en']}")
    print(f"summary ML: {rec['summary']['ml']}")
    if res["alerts"]:
        print("alerts:")
        for a in res["alerts"]:
            print(f"  [{a['severity']}/{a['kind']}] {a['title']}")
            print(f"      {a['message']}")
    else:
        print("alerts:  (none)")
    print(f"reminders ({len(res['reminders'])}):")
    for r in res["reminders"]:
        print(f"  {r['time']}  {r['title']}  until={r['until']}")


async def main():
    _fresh_db()
    for name in DOCS:
        try:
            await _run(name)
        except Exception as e:
            print(f"{name}: FAILED {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
