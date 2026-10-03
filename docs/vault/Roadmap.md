---
tags: [roadmap]
---
# Roadmap

Back to [[Home]].

**Quick (code only)**
- Paginate big lists (timeline, agent history, audit).
- Cache more reads (insights, doctor recommendation) with the same fingerprint idea.
- Gzip and long-cache headers for static files on Render.
- Cheaper visit-note calls ([[Token optimisation]]).

**Small infrastructure**
- Make Redis required in production.
- Run the scheduler as its own single-instance service (or a database advisory lock).
- Job queue (RQ or arq) for uploads and agent tasks, with progress over Redis pub/sub.
- Paid AI tiers and model routing.

**Real scale**
- Object storage (S3 or R2) for the encrypted vault.
- CDN for the frontend, autoscaling API containers, a read replica for doctor reads.

Why these: [[Scalability]]. Current limits: [[Known limits]].
