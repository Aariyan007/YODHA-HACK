---
tags: [testing]
---
# Testing

Back to [[Home]].

- Unit suites (no network, in-memory SQLite): auth, agent core, agent files, agent writes, doctor agent, trends, FHIR, reminders (fake clock), risk, doctors, DDI, decision, classification, speech, static site.
- Live: `scripts/smoke.py`, `scripts/security_sweep.py`, `scripts/e2e_agent.py`, `scripts/test_nginx.py`.
- Load: `scripts/load_test.py` — see [[Scalability]]. Run it inside the backend container: `docker compose exec -e BASE_URL=http://127.0.0.1:8000 backend python scripts/load_test.py --users 100 --seconds 30`, then `scripts/cleanup_test_accounts.py`.
- Test accounts are named `smoke-*` and removed by the cleanup script.
- Gotcha: a long test run exhausts the free Groq daily quota and silently exercises the fallback paths. Check the logs for `RateLimit` before trusting a result.
