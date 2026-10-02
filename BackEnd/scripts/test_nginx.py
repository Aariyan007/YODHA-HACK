"""Checks the nginx edge of the Docker stack: headers, caching, gzip, SPA fallback, body limits, SSE streaming,
rate limiting and log redaction.

    docker compose up -d --build --wait
    cd BackEnd && ./venv/bin/python scripts/test_nginx.py            # BASE_URL=http://localhost:8080 by default

The rate-limit check goes LAST because it locks the sign-in zone for about a minute (all requests from the host
share one IP inside Docker). Run the smoke test and security sweep inside the backend container instead:
    docker compose exec backend python scripts/smoke.py   (set BASE_URL=http://127.0.0.1:8000)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

BASE = os.getenv("BASE_URL", "http://localhost:8080").rstrip("/")
http = httpx.Client(base_url=BASE, timeout=30.0, verify=False)
ROOT = Path(__file__).resolve().parents[2]
fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    fails += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


r = http.get("/")
h = {k.lower(): v for k, v in r.headers.items()}
check("index.html is served and never cached", r.status_code == 200 and h.get("cache-control") == "no-cache", h.get("cache-control", ""))
check("server version is hidden", re.fullmatch(r"nginx", h.get("server", "")) is not None, h.get("server", ""))
for name in ("x-content-type-options", "x-frame-options", "referrer-policy", "permissions-policy", "content-security-policy", "strict-transport-security"):
    check(f"header {name} on the page", name in h)
asset = re.search(r'/assets/[^"]+\.js', r.text)
if asset:
    a = http.get(asset.group(0), headers={"Accept-Encoding": "gzip"})
    check("hashed asset cached for a year", "immutable" in a.headers.get("cache-control", ""), a.headers.get("cache-control", ""))
    check("hashed asset is gzipped", a.headers.get("content-encoding") == "gzip")
check("deep link falls back to the SPA", http.get("/doctor").status_code == 200 and "<div id=\"root\">" in http.get("/doctor").text)
api = http.get("/api/health")
check("API is proxied", api.status_code == 200 and api.json().get("status") == "ok", str(api.json()))
check("API response carries a request id", bool(api.headers.get("x-request-id")))
check("API response carries nosniff", api.headers.get("x-content-type-options") == "nosniff")
check("backend is not reachable around nginx", subprocess.run(["curl", "-s", "-m", "2", "http://localhost:8000/api/health"], capture_output=True).returncode != 0)

# body limits at the edge (nginx answers before the app sees the bytes)
big = http.post("/api/documents", files={"file": ("x.png", b"0" * (12 * 1024 * 1024), "image/png")})
check("upload over 11 MB refused by nginx (413)", big.status_code == 413, f"got {big.status_code}")
big2 = http.post("/api/import/fhir", content=b"0" * (4 * 1024 * 1024), headers={"content-type": "application/json"})
check("hospital import over 3 MB refused by nginx (413)", big2.status_code == 413, f"got {big2.status_code}")

# SSE: stage events must arrive one by one, not all at the end
tok = None
try:
    reg = http.post("/api/auth/register", json={"role": "patient", "name": "Edge Test", "email": f"edge-{os.urandom(3).hex()}@example.com", "password": "edge-pass-123"})
    tok = {"Authorization": f"Bearer {reg.json()['token']}"}
    png = (ROOT / "BackEnd" / "test_docs" / "sunrise_prescription.png").read_bytes()
    job = http.post("/api/documents", files={"file": ("rx.png", png, "image/png")}, headers=tok).json()["jobId"]
    seen, t0 = [], time.time()
    with http.stream("GET", f"/api/jobs/{job}/events") as s:
        for line in s.iter_lines():
            if line.startswith("data: "):
                seen.append(round(time.time() - t0, 2))
                if '"done"' in line or '"error"' in line:
                    break
    spread = seen[-1] - seen[0] if len(seen) > 1 else 0
    check("SSE events stream live (spaced over time, not buffered)", len(seen) >= 5 and spread > 0.2, f"{len(seen)} events over {spread:.2f}s")
except Exception as e:
    check("SSE streaming test", False, f"{type(e).__name__}: {e}")

# log redaction: ask nginx for its recent log lines
logs = subprocess.run(["docker", "compose", "logs", "--no-log-prefix", "--tail", "200", "nginx"], capture_output=True, text=True, cwd=ROOT).stdout
check("nginx log never shows a job id", job not in logs if tok else False)
check("nginx log uses the redacted path", "/api/jobs/<redacted>/events" in logs)

# rate limit last: 10/min + burst 5 on /api/auth/
codes = [http.post("/api/auth/login", json={"email": "rl@example.com", "password": "nope-nope"}).status_code for _ in range(25)]
check("sign-in is rate limited by nginx (429 after the burst)", 429 in codes, f"{codes.count(429)} of 25 were 429")
check("the first few attempts were allowed through", codes[0] == 401, f"first={codes[0]}")

print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
