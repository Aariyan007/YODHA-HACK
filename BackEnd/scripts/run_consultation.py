"""Phase 3 end-to-end demo: scripted 14-line consultation.

Shows:
- flags raised per line (duplicates, clashes, allergies, missing-info)
- doctor-side question suggestions
- the finalized SOAP note
- that the patient timeline is unchanged until /approve
- that one new record appears after /approve
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Make `app`/`ai` importable when run from scripts/.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Load .env from repo root (same pattern as the backend uses).
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(ROOT.parent / ".env")
except Exception:
    pass

# RESET_DB=1 so new Consultation columns actually exist.
os.environ.setdefault("RESET_DB", "1")

from fastapi.testclient import TestClient

from app.auth import create_token
from app.main import app
from app.routers.consultations import DEMO_SCRIPT
from app.seed import DEMO_ID


def _hr(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    with TestClient(app) as client:
        token = create_token(DEMO_ID)
        H = {"Authorization": f"Bearer {token}"}

        # Baseline timeline count
        timeline_before = client.get("/api/patients/me/timeline", headers=H).json()
        print(f"Timeline rows before consultation: {len(timeline_before)}")

        # Create a share link (as the patient)
        share = client.post("/api/shares", headers=H, json={"hours": 24, "scope": "full"}).json()
        print(f"Share token: {share['token'][:8]}…  expires {share['expiresAt']}")

        # Doctor starts the consultation
        r = client.post("/api/consultations/start", headers=H,
                        json={"patientToken": share["token"], "doctorName": "Dr. Rahul Das"})
        r.raise_for_status()
        cid = r.json()["consultationId"]
        print(f"Consultation id: {cid}")

        _hr("Live transcript (14 scripted lines)")
        all_flags: list[dict] = []
        last_suggestions: list[str] = []
        partial_at = {}
        for i, (speaker, text) in enumerate(DEMO_SCRIPT):
            r = client.post(f"/api/consultations/{cid}/line", headers=H,
                            json={"speaker": speaker, "text": text})
            r.raise_for_status()
            data = r.json()
            flags, suggestions, partial = data["flags"], data["suggestions"], data["partial_note"]
            # Report only the NEW flags on this step
            new_flags = flags[len(all_flags):]
            marker = ""
            if new_flags:
                tags = ", ".join(f"[{f['severity']}/{f['kind']}] {f['title']}" for f in new_flags)
                marker = f"   ← flags: {tags}"
            print(f"  {i:>2}. {speaker:>7}: {text}{marker}")
            all_flags = flags
            last_suggestions = suggestions
            if (i + 1) % 3 == 0:
                partial_at[i + 1] = partial

        _hr("All flags raised")
        if not all_flags:
            print("  (none)")
        for f in all_flags:
            print(f"  [{f['severity']}/{f['kind']}] (line {f['lineIndex']}) {f['title']}")
            print(f"      {f['reason']}")

        _hr("Doctor-side question suggestions (latest)")
        if last_suggestions:
            for q in last_suggestions:
                print(f"  • {q}")
        else:
            print("  (none)")

        _hr("Partial SOAP after 12 lines (last Groq pass)")
        print(json.dumps(partial_at.get(12) or {}, indent=2, ensure_ascii=False))

        # Confirm nothing has reached the timeline yet
        timeline_pre_approve = client.get("/api/patients/me/timeline", headers=H).json()
        print(f"\nTimeline rows after transcript, before finalize: {len(timeline_pre_approve)}")
        assert len(timeline_pre_approve) == len(timeline_before), \
            "Timeline MUST NOT change before approve."

        # Finalize
        _hr("Finalize → full SOAP (with source_line indexes)")
        t0 = time.time()
        r = client.post(f"/api/consultations/{cid}/finalize", headers=H)
        r.raise_for_status()
        final = r.json()["finalNote"]
        print(f"(took {time.time() - t0:.1f}s)")
        for k in ("subjective", "objective", "assessment", "plan"):
            v = final.get(k) or {}
            print(f"\n  {k.upper()}  (lines {v.get('source_lines')})")
            print(f"    {v.get('text')}")

        # Patient timeline must still be unchanged
        timeline_pre_approve2 = client.get("/api/patients/me/timeline", headers=H).json()
        assert len(timeline_pre_approve2) == len(timeline_before), \
            "Timeline MUST NOT change before approve (post-finalize check)."
        print(f"\nTimeline rows after finalize: {len(timeline_pre_approve2)} (unchanged ✔)")

        # Approve — doctor accepts without edits
        _hr("Approve → write to patient timeline")
        r = client.post(f"/api/consultations/{cid}/approve", headers=H, json={"edits": {}})
        r.raise_for_status()
        approved = r.json()
        rec = approved["record"]
        print(f"Record id: {rec['id']}  type={rec['type']}  title={rec['title']}")
        print(f"Doctor: {rec['doctor']}  follow-up: {rec['followUp']}")
        print(f"Medications: {[(m['name'], m['dose'], m['schedule']) for m in rec['medications']]}")
        print(f"Alerts saved: {len(approved['alerts'])}")
        print(f"Reminders built: {len(approved['reminders'])}")
        print("\nSummary EN:", rec["summary"]["en"])
        print("Summary ML:", rec["summary"]["ml"])

        # Timeline must have exactly one more record now
        timeline_after = client.get("/api/patients/me/timeline", headers=H).json()
        print(f"\nTimeline rows after approve: {len(timeline_after)}")
        assert len(timeline_after) == len(timeline_before) + 1, \
            f"Expected +1 record, got {len(timeline_after) - len(timeline_before)}"

        _hr("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
