"""Small load test: N people sign up and then browse for a while. Prints requests/s, p50/p95/p99 and errors per route.

    docker compose exec -e BASE_URL=http://127.0.0.1:8000 backend python scripts/load_test.py --users 100 --seconds 30

Run it against the backend directly, not through nginx (nginx rate-limits sign-in to 10/min on purpose). It makes accounts
named smoke-load-*, and removes them with: python scripts/cleanup_test_accounts.py (it deletes every smoke-* test account).
It never calls the AI-backed routes (upload, agent chat, doctor ask), so it spends no Gemini or Groq quota.
"""
import argparse, os, random, statistics, threading, time, uuid
from collections import defaultdict

import httpx

BASE = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
ROUTES = [  # (name, path, weight)
    ("timeline", "/api/patients/me/timeline", 4), ("medicines", "/api/patients/me/medicines", 3),
    ("alerts", "/api/patients/me/alerts", 2), ("insights", "/api/patients/me/insights", 2),
    ("health-check", "/api/patients/me/health-check?ai=false", 1), ("profile", "/api/patients/me", 3),
]
lock = threading.Lock()
lat: dict[str, list[float]] = defaultdict(list)
errs: dict[str, int] = defaultdict(int)


def record(name, ms, ok):
    with lock:
        lat[name].append(ms)
        if not ok:
            errs[name] += 1


def user(i, stop_at, emails):
    email = f"smoke-load-{uuid.uuid4().hex[:8]}@example.test"
    emails.append(email)
    c = httpx.Client(base_url=BASE, timeout=30)
    t = time.perf_counter()
    r = c.post("/api/auth/register", json={"email": email, "password": "Load-test-9x7!pw", "role": "patient", "name": f"Load {i}"})
    record("register", (time.perf_counter() - t) * 1000, r.status_code == 200)
    if r.status_code != 200:
        return
    h = {"Authorization": "Bearer " + r.json()["token"]}
    names, paths, weights = zip(*[(n, p, w) for n, p, w in ROUTES])
    while time.time() < stop_at:
        k = random.choices(range(len(paths)), weights)[0]
        t = time.perf_counter()
        try:
            ok = c.get(paths[k], headers=h).status_code == 200
        except Exception:
            ok = False
        record(names[k], (time.perf_counter() - t) * 1000, ok)
        time.sleep(random.uniform(0.2, 1.0))  # a person reads between clicks


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--seconds", type=int, default=20)
    a = ap.parse_args()
    emails: list[str] = []
    start = time.time()
    stop_at = start + a.seconds
    ts = [threading.Thread(target=user, args=(i, stop_at, emails)) for i in range(a.users)]
    for t in ts:
        t.start()
        time.sleep(0.02)  # arrive over about two seconds instead of in one instant
    for t in ts:
        t.join()
    dur = time.time() - start
    total = sum(len(v) for v in lat.values())
    print(f"{a.users} users, {dur:.0f}s, {total} requests, {total / dur:.1f} req/s, errors {sum(errs.values())}")
    print(f"{'route':14}{'n':>6}{'p50 ms':>9}{'p95 ms':>9}{'p99 ms':>9}{'errors':>8}")
    for n, v in sorted(lat.items()):
        print(f"{n:14}{len(v):>6}{statistics.median(v):>9.0f}{pct(v, .95):>9.0f}{pct(v, .99):>9.0f}{errs[n]:>8}")
    print("cleanup: python scripts/cleanup_test_accounts.py")


main()
