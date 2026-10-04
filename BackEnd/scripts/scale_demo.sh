#!/usr/bin/env bash
# One-command scaling demo for the judges. Run from anywhere with the Docker stack up:
#   bash BackEnd/scripts/scale_demo.sh            (USERS=150 SECS=30 to change the load)
# 1) 1 API copy under load  2) 3 copies under the same load  3) 3 copies, one killed halfway  4) back to 3.
# The load test makes smoke-load-* accounts and every round removes them again.
set -euo pipefail
cd "$(dirname "$0")/../.."
USERS=${USERS:-100}
SECS=${SECS:-25}

run() {
  docker compose exec -T -e BASE_URL=http://nginx:8081 worker python scripts/load_test.py --users "$USERS" --seconds "$SECS" | head -1
  docker compose exec -T backend python scripts/cleanup_test_accounts.py >/dev/null 2>&1 || true
}
scale() {
  docker compose up -d --no-recreate --no-build --scale backend="$1" backend >/dev/null 2>&1
  until [ "$(docker compose ps backend --status running --format '{{.Status}}' | grep -c healthy)" -ge "$1" ]; do sleep 2; done
  sleep 5
}

echo "== 1) one API copy, $USERS people at once =="
scale 1; run
echo "== 2) three API copies, same load =="
scale 3; run
echo "== 3) three copies, one is killed $((SECS / 2))s in =="
( sleep $((SECS / 2)); victim=$(docker compose ps -q backend | head -1); docker kill "$victim" >/dev/null; echo "   [chaos] killed API copy ${victim:0:12}" ) &
run
wait
echo "== 4) bringing it back to three copies =="
scale 3
docker compose ps backend --format "   {{.Name}}  {{.Status}}"
