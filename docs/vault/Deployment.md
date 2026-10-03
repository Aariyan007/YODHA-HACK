---
tags: [deploy]
---
# Deployment

Back to [[Architecture]].

| | Local Docker stack | Hosted (Render) |
| --- | --- | --- |
| Entry | nginx on 8080 and 8443 | one web service |
| Frontend | in the nginx image | served by the API (`static_site.py`) |
| Redis | yes (AOF volume) | none (memory fallback) |
| Files | Docker volume | container disk (wiped on redeploy) |

Run only ONE copy against a database at a time: two copies would each send every reminder.

Optional overlays: `docker-compose.ai.yml` (Laya) and `docker-compose.htr.yml` (TrOCR).

See `DEPLOY.md` and `render.yaml` in the repo. Limits: [[Known limits]]. Scale-out ideas: [[Roadmap]].
