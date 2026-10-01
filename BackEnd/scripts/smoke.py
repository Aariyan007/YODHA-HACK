"""End-to-end smoke test against a RUNNING server.

    cd BackEnd && DEMO_MODE=true ./venv/bin/uvicorn app.main:app --port 8000   # terminal 1
    cd BackEnd && ./venv/bin/python scripts/smoke.py                            # terminal 2
    (BASE_URL=http://host:port to point somewhere else)

Steps: login, upload the prescription test image, check the clash / duplicate
alerts, play the demo consultation, approve it, check the new timeline record,
import the FHIR sample (twice, to prove dedupe), upload the lab report to trigger
the HbA1c trend alert, then POST /api/demo/reset.
Needs DEMO_MODE=true on the server for the first and last steps. It starts and
ends by resetting the demo patient, so it WIPES Ammini's uploads, imports and visits.
Exit code 0 only if every step passes.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
ROOT = Path(__file__).resolve().parents[1]
RX = ROOT / "test_docs" / "sunrise_prescription.png"
PHONE, OTP = "9876543210", "123456"

results: list[tuple[str, bool, str]] = []
ctx: dict = {}


def step(name):
    def deco(fn):
        t0 = time.time()
        try:
            detail = fn() or ""
            ok = True
        except AssertionError as e:
            ok, detail = False, f"assertion: {e}"
        except Exception as e:  # network, JSON, timeouts...
            ok, detail = False, f"{type(e).__name__}: {str(e)[:160]}"
        results.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name:<46} {time.time() - t0:5.1f}s  {detail}", flush=True)
        return fn
    return deco


http = httpx.Client(base_url=BASE, timeout=180.0)


def auth():
    return {"Authorization": f"Bearer {ctx['token']}"}


def get(path, **kw):
    r = http.get(path, **kw)
    assert r.status_code == 200, f"GET {path} -> {r.status_code} {r.text[:120]}"
    return r.json()


def post(path, expect=200, **kw):
    r = http.post(path, **kw)
    assert r.status_code == expect, f"POST {path} -> {r.status_code} {r.text[:160]}"
    return r.json()


def upload_and_wait(path: Path) -> tuple[dict, list[str], bool]:
    """POST the file, follow the SSE stream, return (result, stages, from_cache)."""
    up = post("/api/documents", files={"file": (path.name, path.read_bytes(), "image/png")}, headers=auth())
    stages, result = [], None
    with http.stream("GET", f"/api/jobs/{up['jobId']}/events") as s:
        for line in s.iter_lines():
            if not line.startswith("data: "):
                continue
            ev = json.loads(line[6:])
            if "stage" in ev:
                stages.append(ev["stage"])
            elif "error" in ev:
                raise AssertionError(f"pipeline error: {ev['error']}")
            elif ev.get("done"):
                result = ev["result"]
                break
    assert result, "stream ended without a result"
    return result, stages, up["cached"]


T0 = time.time()
print(f"Smoke test against {BASE}\n")


@step("server is up")
def _():
    h = get("/api/health")
    assert h["status"] == "ok"
    return f"db={h['db']}"


@step("log in as the demo patient")
def _():
    post("/api/auth/otp/request", json={"phone": PHONE})
    r = post("/api/auth/otp/verify", json={"phone": PHONE, "otp": OTP})
    ctx["token"] = r["token"]
    return r["profile"]["name"]


@step("start from the clean demo state (reset)")
def _():
    r = http.post("/api/demo/reset", headers=auth())
    assert r.status_code == 200, f"{r.status_code} (start the server with DEMO_MODE=true)"
    d = r.json()["restored"]
    assert (d["documents"], d["medicines"], d["alerts"]) == (8, 3, 3), d
    return "8 records, 3 medicines, 3 alerts"


@step("upload the prescription test image")
def _():
    assert RX.exists(), f"missing {RX}"
    before = len(get("/api/patients/me/timeline", headers=auth()))
    ctx["tl_before_upload"] = before
    result, stages, cached = upload_and_wait(RX)
    assert stages[:1] == ["read"] and "check" in stages, stages
    ctx["upload"] = result
    return f"{len(stages)} stages, cached={cached}"


@step("2+ clash/duplicate alerts raised, and saved")
def _():
    kinds = [a["kind"] for a in ctx["upload"]["alerts"] if a["kind"] in ("clash", "duplicate")]
    assert len(kinds) >= 2, f"only {kinds}"
    saved = [a for a in get("/api/patients/me/alerts", headers=auth()) if a["kind"] in ("clash", "duplicate")]
    assert len(saved) >= 2
    return f"{kinds.count('clash')} clash, {kinds.count('duplicate')} duplicate"


@step("play the demo consultation (14 lines)")
def _():
    share = post("/api/shares", json={"hours": 1, "scope": "full"}, headers=auth())
    ctx["share"] = share["token"]
    cid = post("/api/consultations/start", json={"patientToken": share["token"], "doctorName": "Dr. Smoke Test"})["consultationId"]
    ctx["cid"] = cid
    ctx["tl_before"] = len(get("/api/patients/me/timeline", headers=auth()))
    H = {"X-Share-Token": share["token"]}
    post(f"/api/consultations/demo/{cid}", headers=H)
    c = get(f"/api/consultations/{cid}", headers=H)
    assert len(c["transcript"]) == 14, len(c["transcript"])
    assert c["flags"], "no safety flags raised"
    assert len(get("/api/patients/me/timeline", headers=auth())) == ctx["tl_before"], "timeline changed before approve"
    return f"{len(c['transcript'])} lines, {len(c['flags'])} flags; timeline unchanged"


@step("finalize + approve the consultation")
def _():
    H = {"X-Share-Token": ctx["share"]}
    fin = post(f"/api/consultations/{ctx['cid']}/finalize", headers=H)
    assert (fin.get("finalNote") or {}).get("subjective"), "no SOAP in finalize"
    ap = post(f"/api/consultations/{ctx['cid']}/approve", json={"edits": {}}, headers=H)
    ctx["approved_id"] = ap["record"]["id"]
    assert ap["record"]["summary"]["en"]
    return f"record {ap['record']['id']}"


@step("new visit record is the first timeline card")
def _():
    tl = get("/api/patients/me/timeline", headers=auth())
    assert len(tl) == ctx["tl_before"] + 1, f"{len(tl)} vs {ctx['tl_before']}+1"
    top = tl[0]
    assert top["id"] == ctx["approved_id"] and top["type"] == "visit", top["type"]
    assert top.get("summary") and top.get("summaryMl"), "missing EN/ML summary"
    return top["title"]


@step("import the FHIR sample hospital record")
def _():
    bundle = get("/api/import/fhir/sample", headers=auth())
    r = post("/api/import/fhir", json=bundle, headers=auth())
    assert r["total"] == 7 and r["imported"]["timelineCards"] == 2, r["imported"]
    assert any(a["kind"] == "duplicate" for a in r["alerts"]), "no duplicate alert for telmisartan"
    ctx["bundle"] = bundle
    return r["message"]


@step("importing the same bundle again adds nothing")
def _():
    before = len(get("/api/patients/me/timeline", headers=auth()))
    r = post("/api/import/fhir", json=ctx["bundle"], headers=auth())
    assert r["alreadyImported"] and r["total"] == 0, r["message"]
    assert len(get("/api/patients/me/timeline", headers=auth())) == before
    return r["message"]


@step("lab upload after the import raises the HbA1c trend alert")
def _():
    lab = ROOT / "test_docs" / "lab_report.png"
    result, _, _ = upload_and_wait(lab)
    trend = [a for a in result["alerts"] if a["kind"] == "trend"]
    assert len(trend) == 1, [a["kind"] for a in result["alerts"]]
    saved = [a for a in get("/api/patients/me/alerts", headers=auth()) if a["kind"] == "trend"]
    assert len(saved) == 1
    assert "7.2, 7.6, 8.2" in saved[0]["message"], saved[0]["message"]
    return saved[0]["message"]


@step("bad FHIR input is refused in plain language")
def _():
    r = http.post("/api/import/fhir", content=b"hello", headers={**auth(), "content-type": "application/json"})
    assert r.status_code == 400 and "not valid JSON" in r.text, (r.status_code, r.text[:80])
    r = http.post("/api/import/fhir", json={"resourceType": "Patient"}, headers=auth())
    assert r.status_code == 400 and "not a FHIR Bundle" in r.text


@step("demo reset restores 8 records / 3 medicines / 3 alerts")
def _():
    out = post("/api/demo/reset", headers=auth())
    assert out["restored"] == {"documents": 8, "medicines": 3, "alerts": 3}, out["restored"]
    assert len(get("/api/patients/me/timeline", headers=auth())) == 8
    assert len(get("/api/patients/me/medicines", headers=auth())) == 3
    assert len(get("/api/patients/me/alerts", headers=auth())) == 3
    assert get("/api/reminders/settings", headers=auth())["remindersEnabled"] is True
    d = out["deleted"]
    return f"removed {d['uploadedDocuments']} upload, {d['importedRecords']} imported, {d['visitNotes']} visit; Telegram reminders on"


passed = sum(1 for _, ok, _ in results if ok)
print(f"\n{passed}/{len(results)} steps passed in {time.time() - T0:.1f}s")
sys.exit(0 if passed == len(results) else 1)
