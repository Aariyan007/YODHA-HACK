# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Phases 1 to 6 of SPEC.md are done:

- Phase 1: FastAPI backend with Supabase (SQLite fallback), seeded demo patient, OTP auth, patient endpoints, share links; Vite + React patient app with login, Home, Timeline, Medicines, Health, Sharing, and a read-only Snapshot page for the doctor QR link.
- Phase 2: upload pipeline (`POST /api/documents` → background thread → SSE stream at `/api/jobs/{id}/events`). Gemini extracts to JSON (`gemini-flash-latest` with fallback cascade); Groq (`openai/gpt-oss-120b` with `reasoning_effort=low`) writes the patient-facing summary and Malayalam translation; `ai/jev_client.py` runs duplicate / allergy / clash / lab-threshold checks. SHA-256 cache in `BackEnd/demo_cache/`, duplicate-upload guard via `Document.file_hash`, best-effort Telegram notify. Also `POST /api/triage` (emergency keyword list first, then rule table, then Groq fallback).
- Phase 3: doctor consultation backend. `/api/consultations/{start,/{id}/line,/{id}/finalize,/{id}/approve,/{id},/demo/{id}}`. Per-line Python safety checks (duplicate / clash / allergy / emergency + missing-info flags at ≥6 lines); Groq rebuilds the partial SOAP note and suggests up to 3 follow-up questions every 3 lines; `/finalize` returns a full SOAP with per-field `source_lines`; `/approve` writes the Document + Medicines + Reminders + Alerts and sends a Telegram notify. AI never diagnoses — the assessment field only restates the doctor. Nothing reaches the patient timeline before `/approve`.
- Phase 4: doctor console frontend at `/console/:token` (outside the patient login guard). Four states: history (reuses `getShareSnapshot`), recording (continuous Web SpeechRecognition with auto-restart, D/P speaker toggle, serial sendLine queue with retry-until-success, live SOAP, flag banners, suggested questions), review (editable S/O/A/P textareas, source-line highlighting, confirm dialog), approved (green tick, TimelineItem preview with EN/ML toggle + Read aloud via SpeechSynthesisUtterance). Entry points: "Open doctor console" next to the QR on Sharing, "Start consultation" on the Snapshot page.
- Phase 5: real reminders. `app/reminder_service.py` runs an APScheduler `BackgroundScheduler` (every 30 s, Asia/Kolkata) started and stopped in the FastAPI lifespan. `run_tick(now, send)` sends one Telegram message per dose per day (dedup key `{medicine_id}@{HH:MM}@{date}` in the store and in the `sent_doses` table, so a restart never resends), a missed-dose message to the family chat once after `missed_after_minutes` unless the dose was marked taken, and refill / follow-up notices the day before (from 09:00 IST, once, tracked in `sent_notices`). Medicines stop after `duration_days` from `start_date`. Per-patient preferences live in `reminder_settings`. Endpoints: `GET/PUT /api/reminders/settings`, `POST /api/reminders/telegram/test`, `POST /api/reminders/{key}/taken` (the old `/api/patients/me/reminders/{key}/taken` shares the same helper), and `POST /api/demo/fire-reminder` + `/api/demo/fire-missed` (404 unless `DEMO_MODE=true`). Frontend: new Reminders tab (toggles, chat ID, test button, demo controls) and "Turn on these reminders" on the upload result.
- Phase 6: trend alert, hospital import, demo tooling, offline build, polish.
  - `app/trends.py::check_trends` (pure Python): after every document save (upload, cached replay, FHIR import) and in seed, if a "higher is worse" lab (HbA1c, FBS, PPBS, LDL, TG, total chol, creatinine, SBP, DBP) has risen in each of the last 3+ stored Observations, it keeps ONE open alert (`kind="trend"`, `severity="high"`) with the real numbers, e.g. "Your HbA1c has risen in each of your last 3 tests: 7.2, 7.6, 8.2. Show this to your doctor." An unread (`resolved=False`) alert for the same test is updated, not duplicated. Tests are matched by lab code, then LOINC, then name. Wording never states a cause or a treatment. Insights chart data comes from stored Observations.
  - `POST /api/import/fhir` (login; Bundle JSON body or multipart `file`; 2 MB cap; `GET /api/import/fhir/sample` serves `BackEnd/samples/aster_medcity_bundle.json`). `app/fhir_import.py` reads Patient, Encounter, Observation (LOINC, BP panels split into SBP/DBP), Condition (ICD-10 kept on `patient.conditions`), MedicationStatement/MedicationRequest, DiagnosticReport; other resource types are skipped and reported. Runs the same `analyse()` checks and Groq EN+ML summary as uploads. Dedupe: each timeline card gets `Document.external_id` (resource type/id + content hash), so re-importing a bundle adds nothing. New columns: `documents.origin/external_id`, `observations.loinc/source`.
  - `app/demo.py` + `routers/demo.py` (404 unless `DEMO_MODE=true`, login needed): `POST /api/demo/reset` restores Ammini to 8 records / 3 medicines / 3 alerts, deletes uploads, imports, consultations, visit notes, sent-dose rows, job caches and `uploads/` files (NOT `demo_cache/`), turns Telegram reminders on. `GET /api/health/deep` makes one tiny call each to DB, Redis, Gemini, Groq, Telegram (`getMe`, sends nothing) and the scheduler; never returns keys. The Reminders page "Demo controls" card has a Reset demo button (inline confirm) and a status line from it.
  - Frontend: dark mode (follows the OS; `<html data-theme="dark|light">` forces one), 48 px touch targets, empty/error states with retry, `npm run build:single` offline build, hash routes in that build. Fixed a `Snapshot` white-screen on invalid/expired links and the doctor console demo auto-feed that did nothing under StrictMode (dev).
  - Security: uploads limited to 10 MB and jpg/png/webp/pdf (checked by magic bytes); CORS from `CORS_ORIGINS` (a bare `*` is ignored unless `DEMO_MODE=true`); fake share tokens answer 404, expired 410 (snapshot and consultations).

Voice SOAP note and reminders are built. Not built: browser push for the phone channel (the toggle only requests notification permission and saves the setting; delivery today is Telegram only).

## Commands

- Backend: `cd BackEnd && ./venv/bin/uvicorn app.main:app --reload --port 8000` (seeds DB on first start). Set `RESET_DB=1` to drop and re-seed. Set `OPENFDA_ENABLE=1` to opt into the OpenFDA fallback (off by default — raw OpenFDA has false positives for almost any pair).
- Frontend: `cd Frontend && npm run dev` (port 5173, proxies `/api` to 8000). `npm run build`. `npm run build:single` writes `Frontend/dist-single/index.html` (one file, mock data, hash routes, runs from `file://`; gitignored).
- Demo backend: `cd BackEnd && DEMO_MODE=true ./venv/bin/uvicorn app.main:app --port 8000`.
- Smoke test (server must be running with `DEMO_MODE=true`; it resets Ammini at start and end): `cd BackEnd && ./venv/bin/python scripts/smoke.py` (13 steps).
- Security sweep against a running server: `cd BackEnd && ./venv/bin/python scripts/security_sweep.py` (run once with and once without `DEMO_MODE`).
- Trend + FHIR unit tests (in-memory SQLite, Groq stubbed): `cd BackEnd && ./venv/bin/python -W ignore scripts/test_trends.py -v` and `scripts/test_fhir.py -v`.
- Pipeline test harness: `cd BackEnd && ./venv/bin/python scripts/make_test_docs.py` to regenerate the Pillow test images, then `./venv/bin/python scripts/run_pipeline.py` to run all three through the pipeline and print stages/alerts/summary/reminders.
- Consultation test harness: `cd BackEnd && RESET_DB=1 ./venv/bin/python scripts/run_consultation.py` — scripted 14-line visit through the full `/start → /line × 14 → /finalize → /approve` path. Prints flags per line, questions, final SOAP, and asserts the timeline is unchanged until approve (+1 after). The script sets `RESET_DB=1` by default, which wipes and re-seeds the DB it points at (it hits Supabase when `DATABASE_URL` is set).
- Reminder unit tests (fake clock, in-memory SQLite, nothing is sent): `cd BackEnd && ./venv/bin/python -W ignore scripts/test_reminders.py -v` (13 cases: once per minute, course dates, missed alert timing, taken cancels, restart safety, refill, appointment).
- No linter yet. Playwright is not installed; end-to-end browser checks are manual (Claude-in-Chrome worked in Phase 6, but cannot open `file://` pages).

## Contract

`Frontend/src/api/client.js` lists every endpoint. `Frontend/src/data/mockData.js` was generated from real backend responses; backend serializers in `BackEnd/app/schemas.py` must keep the same camelCase shapes.

## Gotchas

- `BackEnd/demo_cache/` is gitignored, so a fresh clone has no cached results and the first upload of each test image calls Gemini. The prescription test image's cache entry (`a7618b30...json`) was lost once; it was restored from git history (`git show 54a4ffe:BackEnd/demo_cache/a7618b30e5a763ed0378a69a2e6d3a4c8d22f7daeaef68bb3c3019187f0e2ffc.json`). Gemini's free tier hits 429 quickly, so keep these cache files.
- `scripts/smoke.py` and `POST /api/demo/reset` act on the DB the server points at (Supabase when `DATABASE_URL` is set) and wipe Ammini's uploads, imports and visits.
- Gemini rejects client deadlines under 10 s (`HttpOptions(timeout=...)` is in milliseconds).
- `.env` was committed once in git history (commits `c22276f`..`22c0e01`) but was empty; no key, token or password appears anywhere in history (checked in Phase 6). `uploads/` and `demo_cache/` fictional test files are also in early history.
- `main.jsx` renders under `<StrictMode>`, so every effect mounts twice in dev. Effects that start timers must keep progress in a ref and re-arm after cleanup (the demo auto-feed in `RecordingPanel.jsx` was broken by a `fedRef` guard).
- `Alert.kind` values in use: `interaction`, `duplicate`, `clash`, `allergy`, `lab`, `trend`. `severity` is `high | medium | low`; `resolved=false` means open.
- `Document.type` values: `lab`, `prescription`, `consultation`, `visit` (console approve and FHIR encounters), `scan`. Add new types to `i18n.js` or the card shows the raw key.
- The offline build (`build:single`) is mock-only and uses hash routes. In code, build links with `appPath()` / `appUrl()` / `goLogin()` from `src/routing.js`, never a bare `/path` or `window.location.assign`.
- Claude-in-Chrome cannot open `file://`. To test the offline file, serve `dist-single` with `python3 -m http.server`, and use headless Chrome (`--dump-dom file://...`) for the `file://` check. To audit layouts at 390/1024 px, load routes in fixed-width same-origin iframes and set `documentElement.dataset.theme` to `light` or `dark` (OS dark mode is otherwise what you get).
- A dev backend started with `uvicorn --reload` picks up code edits but not env changes; restart it to change `DEMO_MODE` or `CORS_ORIGINS`.

- `DATABASE_URL` must be the Supabase session pooler URL (`*.pooler.supabase.com`). The direct host is IPv6-only and fails on this network. If Postgres is unreachable the backend falls back to `BackEnd/medithread.db` (SQLite).
- Redis is optional; without it OTP and reminder-taken state live in memory and reset on restart. Dose dedup does not depend on Redis: it is also written to `sent_doses`.
- `add_missing_columns()` (app/database.py) runs at startup and ALTERs new nullable model columns onto existing tables, so upgrading a Postgres DB no longer needs `RESET_DB=1`. It only adds columns; it never changes or drops them.
- Run exactly one backend process with the scheduler against a given DB. Two processes (for example a `--reload` server plus a second `uvicorn`) each run a scheduler and can both send the same dose in the same second. `uvicorn --reload` hot-restarts on any edit under `BackEnd/`, so it also picks up new code and re-runs the startup migration.
- Telegram: the bot token and chat ids are never logged. Errors returned to the UI are plain-language (`ai/telegram.py::send_to`). With `TELEGRAM_BOT_TOKEN` blank the server still starts, the scheduler sends nothing, and `GET /api/reminders/settings` returns `telegramReady: false` (camelCase, like the rest of the API). A chat ID must be numeric (`^-?\d{5,20}$`); the user gets it by messaging the bot first.
- `DEMO_MODE=true` (env, not set by default) enables `/api/demo/fire-reminder`, `/api/demo/fire-missed`, `/api/demo/reset` and `/api/health/deep` (all need a login, 404 otherwise) and makes the settings response return `demoMode: true`, which shows the "Demo controls" card on the Reminders page.
- Models in SPEC were retired. Gemini: cascade `gemini-flash-latest` → `gemini-3.5-flash` → `gemini-3.7-flash` → `gemini-3.8-flash` (free tier quota exhausts the latest; cascade falls through). Groq: `openai/gpt-oss-120b` with `reasoning_effort=low` and `max_tokens=1500` (gpt-oss burns tokens on hidden reasoning; low budget truncates visible output).
- `BackEnd/uploads/` and `BackEnd/demo_cache/` are gitignored. Cache keys are the file SHA-256; the cached result is replayed instantly on re-upload. Resetting the DB with the cache intact still produces a saved Document on re-upload via `_persist_result`.
- SSE endpoint `/api/jobs/{id}/events` is intentionally unauthenticated — the unguessable `jobId` (uuid4) is the key, because `EventSource` cannot send `Authorization`.
- Consultation endpoints are **not** behind the patient JWT. `/start` is unauthenticated (the share token in the body is the credential); every other call must send `X-Share-Token: <token>` matching `Consultation.share_token`, and the share link's expiry is re-checked on each call. The doctor console lives at `/console/:token` *outside* the patient login guard.
- The frontend has no `AppShell.jsx`, `DoctorView.jsx`, `Profile.jsx`, `index.css`, Atkinson Hyperlegible font — the Phase 4 brief referred to a different codebase variant. Entry points to the console are instead on `Sharing.jsx` (owner's QR screen) and `Snapshot.jsx` (doctor's read-only snapshot).
- Doctor-console in-progress state lives in React state only (no localStorage). A browser refresh loses the consultationId, so a mid-visit refresh starts a new visit; `getConsultation(id, token)` is available in the API client if deep-link restore is ever needed.

## Layout

- `BackEnd/` is Python (FastAPI, venv in `BackEnd/venv`). `Frontend/` is Vite + React (JavaScript). No root workspace config.
- `.env` sits at the repo root and is gitignored. It is shared config for both sides, not per-package.

## Environment variables (root `.env`)

Names only. Never print or commit the values.

- Backend: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, optional `DEMO_MODE`, `OPENFDA_ENABLE`, `RESET_DB`, `CORS_ORIGINS` (comma-separated allowed browser origins; default is the two local dev URLs)
- Frontend (Vite, so the `VITE_` prefix): `VITE_USE_MOCK` (toggles mock data instead of the real API), `VITE_API_URL`

See `README.md` for start-up steps, the demo click path and known limits.

## Phase 4 end-to-end

Playwright is not installed and the Claude-in-Chrome extension was not connected during the build, so the end-to-end check was done by driving the live HTTP API with `curl` + verifying the console UI compiles cleanly. Confirmed results against a running `uvicorn` + a `/share/*` token issued to the demo patient (`9876543210`):

- `POST /api/consultations/start` with `patientToken` returns a 12-char `consultationId`. No bearer token needed.
- `POST /api/consultations/demo/{id}` with `X-Share-Token: <t>` feeds all 14 lines in one call. Resulting state (`GET /api/consultations/{id}`):
  - 14 transcript lines
  - 8 flags: metformin & atorvastatin duplicates + missing-allergy + missing-follow-up at line 5; a clarithromycin+atorvastatin clash and a Glycomet duplicate as new meds are introduced
  - 3 suggested follow-up questions
  - Partial SOAP with S/O/A/P all filled by line 12
- `POST /api/consultations/{id}/finalize` returns a SOAP note with per-field `source_lines` (S:[1,3,5,7], O:[8], A:[9], P:[9,10,12]).
- `POST /api/consultations/{id}/approve` writes `type=visit` to the patient timeline, saves 8 alerts + 5 reminders, Telegram notify is best-effort. Timeline grew 10 → 11; the new row is the first card, with English and Malayalam summaries both populated.

To replay the console UI by hand against the running stack:

1. Start the backend (`uvicorn`) and the frontend (`npm run dev`). Set `VITE_USE_MOCK=false` in `.env` to hit the real backend; keep `true` to run the console on scripted mock responses.
2. Log in as the demo patient (`9876543210`, any 6-digit OTP) and open the Sharing tab.
3. Create a share link, then click **Open doctor console** (or paste the token into `/console/<token>` in a new tab). The console does not require the patient login — it only needs the share token in the URL.
4. On the history panel, keep the default doctor name or edit it; click **Play demo conversation** to run the scripted 14-line visit, or **Start recording** to use the microphone (Chrome only; the page shows a text-input fallback otherwise).
5. Watch flags accumulate: Metformin and Atorvastatin duplicates fire at line 6, missing-info flags around line 6, the Clarithromycin + Atorvastatin clash at line 10, Glycomet duplicate at line 11. The "Consider asking" box refreshes every 3 lines.
6. Click **Stop and review**. `/finalize` runs; four editable SOAP cards appear with source-line badges. Click a badge to highlight the transcript lines that produced that field.
7. Edit any field (the card gets an "edited" pill), then **Approve and send to patient**. Confirm the dialog.
8. The approved panel shows the TimelineItem preview with the EN / മലയാളം toggle and **Read aloud**.
9. Switch back to the patient app (patient login tab) and reload Timeline — the new visit is the first card, with the Malayalam summary available via the language toggle in the top bar.

Screenshots at 820 px (tablet) and 390 px (phone) are easiest with Chrome DevTools' device toolbar (⌘⇧M), one per state × two widths = 8 captures. Responsive breakpoints baked into `styles.css`:

- `.console-grid` (history) collapses to a single column below 820 px.
- `.console-record-grid` (recording) collapses below 820 px.
- `.console-review-grid` (review) collapses below 960 px (so review stays single-column on both tablet and phone, which matches the brief's "must not overflow on a phone").
- All buttons use the global `button` 48-px-tall rule in `.console-cta`.

`npm run build` passes (326 kB JS, 10 kB CSS). `build:single` was added in Phase 6.
