"""Security checks against a RUNNING server. Prints PASS/FAIL for each check.

    cd BackEnd && ./venv/bin/python scripts/security_sweep.py          # server on :8000
    BASE_URL=... ./venv/bin/python scripts/security_sweep.py

Checks: every /api/patients/* route gives 401 with no token (and with a junk token), fake and expired share tokens
give 404/410, uploads over 10 MB (413) and types other than jpg/png/webp/pdf (415) are refused, CORS never answers "*"
and doesn't echo a foreign origin, and the demo only routes are 404 unless DEMO_MODE=true.
An expired share link is made straight in the database and deleted again.
"""
from __future__ import annotations

import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
http = httpx.Client(base_url=BASE, timeout=30.0)
fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    fails += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


# ---- every /api/patients/* route needs a login ----
spec = http.get("/openapi.json").json()
routes = [(m.upper(), p) for p, ops in spec["paths"].items() if p.startswith("/api/patients/") for m in ops if m in ("get", "post", "put", "delete", "patch")]
print(f"-- {len(routes)} /api/patients/* routes found in OpenAPI")
for method, path in sorted(routes):
    url = path.replace("{key}", "med1_0800")
    for label, headers in (("no token", {}), ("junk token", {"Authorization": "Bearer not.a.jwt"})):
        r = http.request(method, url, headers=headers)
        check(f"{method} {path} with {label} -> 401", r.status_code == 401, f"got {r.status_code}")

# ---- other login-only routes ----
for method, path in [("POST", "/api/documents"), ("POST", "/api/shares"), ("POST", "/api/import/fhir"), ("GET", "/api/import/fhir/sample"),
                     ("GET", "/api/reminders/settings"), ("PUT", "/api/reminders/settings"), ("POST", "/api/reminders/telegram/test")]:
    r = http.request(method, path)
    check(f"{method} {path} with no token -> 401", r.status_code == 401, f"got {r.status_code}")

# ---- share tokens ----
fake = secrets.token_urlsafe(16)
r = http.get(f"/api/shares/{fake}/snapshot")
check("fake share token: snapshot -> 404", r.status_code == 404, f"got {r.status_code}")
r = http.post("/api/consultations/start", json={"patientToken": fake})
check("fake share token: consultation start -> 404", r.status_code == 404, f"got {r.status_code}")
r = http.post("/api/consultations/abc123/line", json={"text": "hi", "speaker": "doctor"}, headers={"X-Share-Token": fake})
check("fake share token: consultation line -> 404", r.status_code == 404, f"got {r.status_code}")
r = http.post("/api/consultations/abc123/line", json={"text": "hi", "speaker": "doctor"})
check("no share token: consultation line -> 401", r.status_code == 401, f"got {r.status_code}")

from sqlalchemy import delete  # noqa: E402  (imports the app's DB; only needed for the expired-link check)
from app.database import SessionLocal  # noqa: E402
from app.models import ShareLink  # noqa: E402
from app.seed import DEMO_ID  # noqa: E402

expired = "sweep-" + secrets.token_urlsafe(8)
with SessionLocal() as db:
    db.add(ShareLink(token=expired, patient_id=DEMO_ID, scope="full", expires_at=datetime.now(timezone.utc) - timedelta(hours=1)))
    db.commit()
try:
    r = http.get(f"/api/shares/{expired}/snapshot")
    check("expired share token: snapshot -> 410", r.status_code == 410, f"got {r.status_code}")
    r = http.post("/api/consultations/start", json={"patientToken": expired})
    check("expired share token: consultation start -> 410", r.status_code == 410, f"got {r.status_code}")
finally:
    with SessionLocal() as db:
        db.execute(delete(ShareLink).where(ShareLink.token == expired))
        db.commit()

# ---- uploads: size and type ----
def register(role):
    r = http.post("/api/auth/register", json={"role": role, "name": f"Sweep {role}", "email": f"sweep-{role}-{secrets.token_hex(4)}@example.com", "password": "sweep-pass-123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


H = register("patient")  # works with DEMO_MODE on or off
png = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def up(name, data, mime):
    return http.post("/api/documents", files={"file": (name, data, mime)}, headers=H, timeout=60.0)


r = up("big.png", png + b"0" * (10 * 1024 * 1024), "image/png")
check("upload 10 MB + a bit -> 413", r.status_code == 413, f"got {r.status_code}")
for name, data, mime in [("evil.exe", b"MZ\x90\x00" + b"0" * 100, "application/octet-stream"),
                         ("notes.txt", b"hello world", "text/plain"),
                         ("fake.png", b"MZ\x90\x00 pretending to be a png", "image/png"),
                         ("page.html", b"<html><script>1</script></html>", "text/html"),
                         ("anim.gif", b"GIF89a" + b"0" * 50, "image/gif")]:
    r = up(name, data, mime)
    check(f"upload {name} ({mime}) -> 415", r.status_code == 415, f"got {r.status_code}")
r = up("empty.png", b"", "image/png")
check("upload empty file -> 400", r.status_code == 400, f"got {r.status_code}")

# ---- accounts and roles (Phase 8) ----
D = register("doctor")
for path in ("/api/patients/me", "/api/patients/me/timeline", "/api/care/invite", "/api/documents"):
    method = "POST" if path in ("/api/care/invite", "/api/documents") else "GET"
    r = http.request(method, path, headers=D)
    check(f"doctor token on {method} {path} -> 401", r.status_code == 401, f"got {r.status_code}")
for method, path in (("GET", "/api/doctor/patients"), ("POST", "/api/doctor/link"), ("GET", "/api/doctor/patients/x/snapshot"), ("POST", "/api/doctor/patients/x/console-token")):
    r = http.request(method, path, headers=H, json={"code": "AAAA-AAAA"} if method == "POST" else None)
    check(f"patient token on {method} {path} -> 401", r.status_code == 401, f"got {r.status_code}")
    r = http.request(method, path, json={"code": "AAAA-AAAA"} if method == "POST" else None)
    check(f"no token on {method} {path} -> 401", r.status_code == 401, f"got {r.status_code}")
me = http.get("/api/auth/me", headers=H).json()
r = http.get(f"/api/doctor/patients/{me['id']}/snapshot", headers=D)
check("unlinked doctor on a real patient -> 404", r.status_code == 404, f"got {r.status_code}")
r = http.post(f"/api/doctor/patients/{me['id']}/console-token", headers=D)
check("unlinked doctor cannot get a console token -> 404", r.status_code == 404, f"got {r.status_code}")
r = http.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-pass-1"})
check("login with an unknown email -> 401, generic text", r.status_code == 401 and r.json()["detail"] == "Email or password is incorrect.", f"got {r.status_code}")
r = http.post("/api/auth/register", json={"role": "admin", "name": "X Y", "email": "a@b.co", "password": "longenough1"})
check("cannot register an admin role -> 422", r.status_code == 422, f"got {r.status_code}")
if http.get("/api/auth/config").json().get("demoLogin") is False:
    check("OTP login is 404 with DEMO_MODE off", http.post("/api/auth/otp/request", json={"phone": "9876543210"}).status_code == 404)

# ---- CORS ----
for origin in ("http://localhost:5173", "https://evil.example"):
    r = http.options("/api/patients/me", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    allow = r.headers.get("access-control-allow-origin")
    check(f"CORS preflight from {origin}: never '*'", allow != "*", f"allow-origin={allow!r}")
r = http.options("/api/patients/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
check("CORS: a foreign origin is not allowed", r.headers.get("access-control-allow-origin") is None)

# ---- demo-only routes ----
demo_on = bool(http.get("/api/reminders/settings", headers=H).json().get("demoMode"))
print(f"-- server DEMO_MODE appears {'ON' if demo_on else 'OFF'}")
if not demo_on:
    check("/api/health/deep is 404 with DEMO_MODE off", http.get("/api/health/deep", headers=H).status_code == 404)
    check("/api/demo/fire-reminder is 404 with DEMO_MODE off", http.post("/api/demo/fire-reminder", headers=H).status_code == 404)

try:
    from scripts.cleanup_test_accounts import cleanup  # noqa: E402
    print(f"cleanup: removed {cleanup()} throwaway account(s)")
except Exception as e:  # never fail a run because of cleanup
    print(f"cleanup skipped: {type(e).__name__}")

print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
