# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Phase 1 of SPEC.md is done: FastAPI backend with seeded demo patient, and a Vite + React patient app. Upload, AI extraction, drug checks, Telegram and the doctor console are not built yet.

## Commands

- Backend: `cd BackEnd && ./venv/bin/uvicorn app.main:app --reload --port 8000` (seeds DB on first start)
- Frontend: `cd Frontend && npm run dev` (port 5173, proxies `/api` to 8000), `npm run build`
- No tests or linter yet.

## Contract

`Frontend/src/api/client.js` lists every endpoint. `Frontend/src/data/mockData.js` was generated from real backend responses; backend serializers in `BackEnd/app/schemas.py` must keep the same camelCase shapes.

## Gotchas

- `DATABASE_URL` must be the Supabase session pooler URL (`*.pooler.supabase.com`). The direct host is IPv6-only and fails on this network. If Postgres is unreachable the backend falls back to `BackEnd/medithread.db` (SQLite).
- Redis is optional; without it OTP and reminder-taken state live in memory and reset on restart.
- Models in SPEC were retired: use Gemini `gemini-3.8-flash` (retry on 503) and Groq `openai/gpt-oss-120b`.

## Layout

- `BackEnd/` is Python (FastAPI, venv in `BackEnd/venv`). `Frontend/` is Vite + React (JavaScript). No root workspace config.
- `.env` sits at the repo root and is gitignored. It is shared config for both sides, not per-package.

## Environment variables (root `.env`)

Names only. Never print or commit the values.

- Backend: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- Frontend (Vite, so the `VITE_` prefix): `VITE_USE_MOCK` (toggles mock data instead of the real API), `VITE_API_URL`

This implies a Vite frontend, a backend backed by a database and Redis with JWT auth, Gemini and Groq as LLM providers, and Telegram notifications. Confirm against the real code once it exists.
