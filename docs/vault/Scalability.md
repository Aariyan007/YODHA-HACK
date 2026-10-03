---
tags: [scalability, performance]
---
# Scalability

Back to [[Home]]. Measured with `BackEnd/scripts/load_test.py` (100 simultaneous users, no AI calls, run against the backend container).

| | Before | After |
| --- | --- | --- |
| Errors | about 100 of 240 requests | 0 of 1,912 |
| Throughput | about 5 req/s | about 60 req/s |
| Page time | 30 s (timeouts) | p50 about 0.9 s, p95 about 1.4 s |

## Why it broke
Each request holds one database connection from its login check to its end. The server has a small worker-thread pool. With 100 requests at once, some held connections while waiting for a thread, and the threads waited for connections. Everything stalled until the timeout. The pool was also only 5 connections.

## What fixed it
- **In-flight cap:** at most 30 API requests run at once, the rest queue cheaply (`app/concurrency.py`).
- **Bigger pool:** 20 + 20 on the Supabase transaction pooler.
- **Bounded password hashing:** each scrypt run needs about 16 MB, so only 3 run at once (a burst used 640 MB of a 768 MB container).
- **Indexes:** documents and observations by patient and date, open alerts, audit by actor.
- **Cache:** the AI health review is reused for 2 minutes, only while the record is unchanged.
- **Daily limits per person:** uploads 30, doctor search 60, AI review 40, assistant 80. They protect the shared free AI quota.
- **Slow-request log:** anything over 1 second is logged as a warning.

## Still true
One backend process (it owns the scheduler), one Redis, free AI quotas. See [[Roadmap]] for the next steps and [[Token optimisation]] for AI cost.

Related: [[Testing]], [[Deployment]].
