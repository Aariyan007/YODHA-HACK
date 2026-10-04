---
tags: [architecture]
---
# Architecture

Back to [[Home]].

```mermaid
flowchart LR
  P[Patient browser] --> N[nginx]
  D[Doctor browser] --> N
  N -->|/api| API[FastAPI backend<br/>3 copies + workers + scheduler]
  API --> PG[(Supabase Postgres)]
  API --> RD[(Redis)]
  API --> V[Encrypted vault]
  API --> GEM[Gemini: reads documents]
  API --> GRQ[Groq: summaries, agent, judge, Whisper]
  API --> EL[ElevenLabs: speech to text]
  API --> DDI[(DDInter drug interactions)]
  API --> FDA[openFDA labels]
  SCH[Scheduler every 30 s] --> TG[Telegram]
  API --- SCH
```

## Layers
| Layer | Folder | Rule |
| --- | --- | --- |
| HTTP | `BackEnd/app/routers/` | thin: auth, patients, documents, consultations, reminders, doctors, shares, care, agent, admin |
| Domain | `BackEnd/app/` | plain Python: risk, trends, labs, vitals, reminder_service, fhir_import, vault, store |
| Agent | `BackEnd/app/agent/` | planner, loop, executor, registry, permissions, judge, tasks, audit — see [[Agent]] |
| AI | `BackEnd/ai/` | everything that calls a model — see [[AI services]] |
| Frontend | `Frontend/src/` | see [[Frontend]] |

**The rule inside every layer: models write words, Python decides facts.** Risk levels, the emergency banner, interaction alerts, trend alerts and every permission check never depend on a model.

## Two deployment shapes
See [[Deployment]]: local Docker stack (nginx + Redis) and the Render copy (one container, no Redis).

Related: [[Request flows]], [[Safety and privacy]], [[Scalability]].
