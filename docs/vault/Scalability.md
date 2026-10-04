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

## AWS in a box (no cloud account)
| Cloud idea | Here |
| --- | --- |
| Load balancer | nginx over 3 API copies, least connections, skips a dead copy and retries on another |
| Queue + serverless workers | uploads go on a Redis queue, worker containers run them; a dead worker's job is put back |
| Leader election | 2 scheduler containers, one leader via a Redis lease, each dose sent once |
| Circuit breakers | a failing AI service is skipped for 30 s and the fallback answers at once |
| Bulkheads + load shedding | separate fast and AI lanes; overload gets a fast "busy" (503 + Retry-After) |
| Auto Scaling | `scripts/autoscale.py` scales API copies 2 to 6 and workers 1 to 4 from live load |
| CloudWatch | live panel on `/admin`: requests/s, latency, errors, copies, workers, schedulers, queue, breakers |

| | 1 API copy | 3 API copies | 3 copies, one killed halfway |
| --- | --- | --- | --- |
| Requests per second | about 57 | about 100 | about 101 |
| Typical page (p50) | about 1,150 ms | about 345 ms | about 345 ms |
| Errors | 0 | 0 | 0 |

The autoscaler went from 2 to 6 copies in about 15 s under 150 people, 0 errors in 4,644 requests. Past 3 copies throughput stays near 100 req/s: the remote database is the limit now.

Demo: `bash BackEnd/scripts/scale_demo.sh`. Next steps: [[Roadmap]]. AI cost: [[Token optimisation]].

Related: [[Testing]], [[Deployment]].
