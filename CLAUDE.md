# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Phases 1 and 2 of SPEC.md are done:

- Phase 1: FastAPI backend with Supabase (SQLite fallback), seeded demo patient, OTP auth, patient endpoints, share links; Vite + React patient app with login, Home, Timeline, Medicines, Health, Sharing, and a read-only Snapshot page for the doctor QR link.
- Phase 2: upload pipeline (`POST /api/documents` → background thread → SSE stream at `/api/jobs/{id}/events`). Gemini extracts to JSON (`gemini-flash-latest` with fallback cascade); Groq (`openai/gpt-oss-120b` with `reasoning_effort=low`) writes the patient-facing summary and Malayalam translation; `ai/jev_client.py` runs duplicate / allergy / clash / lab-threshold checks. SHA-256 cache in `BackEnd/demo_cache/`, duplicate-upload guard via `Document.file_hash`, best-effort Telegram notify. Also `POST /api/triage` (emergency keyword list first, then rule table, then Groq fallback).

Doctor console, voice SOAP note, and reminder push are not built yet.

## Commands

- Backend: `cd BackEnd && ./venv/bin/uvicorn app.main:app --reload --port 8000` (seeds DB on first start). Set `RESET_DB=1` to drop and re-seed. Set `OPENFDA_ENABLE=1` to opt into the OpenFDA fallback (off by default — raw OpenFDA has false positives for almost any pair).
- Frontend: `cd Frontend && npm run dev` (port 5173, proxies `/api` to 8000). `npm run build`.
- Pipeline test harness: `cd BackEnd && ./venv/bin/python scripts/make_test_docs.py` to regenerate the Pillow test images, then `./venv/bin/python scripts/run_pipeline.py` to run all three through the pipeline and print stages/alerts/summary/reminders.
- No tests or linter yet.

## Contract

`Frontend/src/api/client.js` lists every endpoint. `Frontend/src/data/mockData.js` was generated from real backend responses; backend serializers in `BackEnd/app/schemas.py` must keep the same camelCase shapes.

## Gotchas

- `DATABASE_URL` must be the Supabase session pooler URL (`*.pooler.supabase.com`). The direct host is IPv6-only and fails on this network. If Postgres is unreachable the backend falls back to `BackEnd/medithread.db` (SQLite).
- Redis is optional; without it OTP and reminder-taken state live in memory and reset on restart.
- Models in SPEC were retired. Gemini: cascade `gemini-flash-latest` → `gemini-3.5-flash` → `gemini-3.7-flash` → `gemini-3.8-flash` (free tier quota exhausts the latest; cascade falls through). Groq: `openai/gpt-oss-120b` with `reasoning_effort=low` and `max_tokens=1500` (gpt-oss burns tokens on hidden reasoning; low budget truncates visible output).
- `BackEnd/uploads/` and `BackEnd/demo_cache/` are gitignored. Cache keys are the file SHA-256; the cached result is replayed instantly on re-upload. Resetting the DB with the cache intact still produces a saved Document on re-upload via `_persist_result`.
- SSE endpoint `/api/jobs/{id}/events` is intentionally unauthenticated — the unguessable `jobId` (uuid4) is the key, because `EventSource` cannot send `Authorization`.

## Layout

- `BackEnd/` is Python (FastAPI, venv in `BackEnd/venv`). `Frontend/` is Vite + React (JavaScript). No root workspace config.
- `.env` sits at the repo root and is gitignored. It is shared config for both sides, not per-package.

## Environment variables (root `.env`)

Names only. Never print or commit the values.

- Backend: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- Frontend (Vite, so the `VITE_` prefix): `VITE_USE_MOCK` (toggles mock data instead of the real API), `VITE_API_URL`

This implies a Vite frontend, a backend backed by a database and Redis with JWT auth, Gemini and Groq as LLM providers, and Telegram notifications. Confirm against the real code once it exists.
