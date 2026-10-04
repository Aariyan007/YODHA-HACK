"""Autoscaler for the local Docker stack (our Auto Scaling group). Runs on your machine, not in a container.

    python3 BackEnd/scripts/autoscale.py                 # from the repo root, Ctrl+C to stop
    python3 BackEnd/scripts/autoscale.py --dry-run       # only print what it would do

Every 5 s it reads the live numbers the API copies write to Redis (requests per second, how many requests are
waiting in each copy, how many uploads are queued) and sets the number of copies:
  API copies:  enough for TARGET_RPS requests/s each, plus one more if requests are waiting. Between MIN and MAX.
  Workers:     one per 3 queued uploads, at least 1.
It scales up straight away and down only after 60 s of low load, one copy at a time, so it doesn't flap.
It uses `docker compose`, so no cloud account or Docker socket inside a container is needed. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET_RPS = 25          # one copy handled about 33 req/s in the load test, so keep headroom
MIN_API, MAX_API = 2, 6
MIN_WORKERS, MAX_WORKERS = 1, 4
COOLDOWN = 60

# One Redis call that gathers everything: req/s over the last 15 s, waiting requests per copy, queue depth.
LUA = """
local now = tonumber(redis.call('TIME')[1])
local b = now - now % 5
local req = 0
for i = 1, 3 do
  local v = redis.call('HGET', 'm:' .. (b - 5 * i), 'req')
  if v then req = req + tonumber(v) end
end
local copies, waiting = 0, 0
for _, k in ipairs(redis.call('KEYS', 'hb:api:*')) do
  copies = copies + 1
  local raw = redis.call('GET', k)
  if raw then
    local ok, hb = pcall(cjson.decode, raw)
    if ok and hb.lanes then
      for _, lane in pairs(hb.lanes) do waiting = waiting + (lane.waiting or 0) end
    end
  end
end
local workers = #redis.call('KEYS', 'hb:worker:*')
return cjson.encode({rps = req / 15, copies = copies, waiting = waiting, queue = redis.call('LLEN', 'q:pipeline'), workers = workers})
"""


def sh(*args: str) -> str:
    return subprocess.run(["docker", "compose", *args], cwd=ROOT, capture_output=True, text=True, timeout=120).stdout


def read() -> dict | None:
    out = sh("exec", "-T", "redis", "redis-cli", "--raw", "EVAL", LUA, "0").strip()
    try:
        return json.loads(out)
    except ValueError:
        return None


def running(service: str) -> int:
    return len([l for l in sh("ps", service, "--status", "running", "-q").splitlines() if l.strip()])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--every", type=float, default=5)
    a = ap.parse_args()
    low_since = {"backend": None, "worker": None}
    print(f"autoscaler: API {MIN_API}-{MAX_API} copies at {TARGET_RPS} req/s each, workers {MIN_WORKERS}-{MAX_WORKERS}")
    while True:
        m = read()
        if m is None:
            print("can't read Redis (is the stack up?)")
            time.sleep(a.every)
            continue
        want = {
            "backend": min(MAX_API, max(MIN_API, math.ceil(m["rps"] / TARGET_RPS) + (1 if m["waiting"] > 0 else 0))),
            "worker": min(MAX_WORKERS, max(MIN_WORKERS, math.ceil(m["queue"] / 3) + (1 if m["queue"] else 0))),
        }
        have = {"backend": running("backend"), "worker": running("worker")}
        stamp = time.strftime("%H:%M:%S")
        line = f"{stamp}  {m['rps']:6.1f} req/s  waiting {m['waiting']:3d}  queue {m['queue']:3d}  | API {have['backend']}->{want['backend']}  workers {have['worker']}->{want['worker']}"
        for svc in ("backend", "worker"):
            target = want[svc]
            if target > have[svc]:
                low_since[svc] = None
                line += f"  [scale {svc} up to {target}]"
                if not a.dry_run:
                    sh("up", "-d", "--no-recreate", "--no-build", "--scale", f"{svc}={target}", svc)
            elif target < have[svc]:
                low_since[svc] = low_since[svc] or time.time()
                if time.time() - low_since[svc] >= COOLDOWN:
                    target = have[svc] - 1   # down one at a time
                    line += f"  [scale {svc} down to {target}]"
                    if not a.dry_run:
                        sh("up", "-d", "--no-recreate", "--no-build", "--scale", f"{svc}={target}", svc)
                    low_since[svc] = time.time()
            else:
                low_since[svc] = None
        print(line, flush=True)
        time.sleep(a.every)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nautoscaler stopped")
