# MediThread

A patient health-record app for an elderly patient and the people who care for them: upload a prescription or lab photo, get a plain-language summary (English and Malayalam), safety warnings, medicine reminders on Telegram, and a doctor console that turns a spoken visit into a SOAP note.

The AI never diagnoses and never tells anyone what to take. It restates what the document or the doctor said, and flags things to show a doctor.

- `BackEnd/` FastAPI, SQLAlchemy (Supabase Postgres, SQLite fallback), APScheduler. Gemini reads documents, Groq writes summaries and translations. Safety checks are plain Python.
- `Frontend/` Vite + React (JavaScript).

## Start it

You need Python 3.12+ and Node 20+. Put a `.env` in the repo root (see the table below). The backend creates and seeds its tables on first start.

```bash
# terminal 1: backend (port 8000)
cd BackEnd
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt   # first time only
./venv/bin/uvicorn app.main:app --reload --port 8000

# terminal 2: frontend (port 5173, proxies /api to 8000)
cd Frontend
npm install                                                            # first time only
npm run dev
```

Open http://localhost:5173 and log in as the demo patient: phone `9876543210`, any 6 digits.

Run exactly one backend process per database. Each one starts a reminder scheduler, and two can send the same dose.

## Environment variables

Set them in the root `.env` (gitignored). Never commit values.

| Name | Used by | Notes |
| --- | --- | --- |
| `DATABASE_URL` | backend | Supabase **session pooler** URL (`*.pooler.supabase.com`). If missing or unreachable the backend uses `BackEnd/medithread.db` (SQLite). |
| `REDIS_URL` | backend | Optional. Without it OTP and "taken" state live in memory and reset on restart. |
| `JWT_SECRET` | backend | Signs login tokens. Set a long random value outside local dev. |
| `GEMINI_API_KEY` | backend | Reads uploaded documents. Free tier runs out; the code falls through a model list. |
| `GROQ_API_KEY` | backend | Summaries, Malayalam, consultation notes. |
| `TELEGRAM_BOT_TOKEN` | backend | Reminder delivery. Blank = server runs, nothing is sent. |
| `TELEGRAM_CHAT_ID` | backend | Default chat for the demo patient. Get yours by messaging the bot first. |
| `CORS_ORIGINS` | backend | Comma-separated browser origins allowed to call the API. Default: the two local dev URLs. A bare `*` is ignored unless `DEMO_MODE=true`. |
| `DEMO_MODE` | backend | `true` turns on the demo-only endpoints (see below). Off by default. |
| `OPENFDA_ENABLE` | backend | `1` adds an OpenFDA lookup for unknown drug pairs. Off by default (too many false positives). |
| `RESET_DB` | backend | `1` drops all tables and re-seeds at startup. |
| `VITE_USE_MOCK` | frontend | `true` runs the UI on built-in mock data, no backend needed. |
| `VITE_API_URL` | frontend | Backend base URL. Empty = same origin (Vite proxy). |

## Demo mode

Start the backend with `DEMO_MODE=true`:

```bash
cd BackEnd && DEMO_MODE=true ./venv/bin/uvicorn app.main:app --port 8000
```

This enables, for a logged-in user only (404 otherwise):

- `POST /api/demo/fire-reminder` and `/api/demo/fire-missed`: send a dose reminder or a missed-dose alert to Telegram now.
- `POST /api/demo/reset`: put Ammini back to the clean seed (8 records, 3 medicines, 3 alerts), delete uploads, imports, consultations and sent-dose rows, and turn her Telegram reminders on. `BackEnd/demo_cache/` is kept.
- `GET /api/health/deep`: one tiny call each to the database, Redis, Gemini, Groq, Telegram (read-only `getMe`) and the scheduler. No keys are ever returned.

On the **Reminders** tab a "Demo controls" card shows the services status line, the two fire buttons and **Reset demo**.

Keep the files in `BackEnd/demo_cache/`. They replay the three test images instantly, so the demo does not depend on Gemini quota. The cache is gitignored; copy it to any new machine.

### Offline backup

```bash
cd Frontend && npm run build:single      # writes Frontend/dist-single/index.html
```

One self-contained file that opens from `file://` with no server. It is pinned to mock data and uses `#/` routes, so login, timeline, upload, hospital import and the doctor console demo all work offline. It cannot talk to the real backend.

## The 4-minute demo

Before you start: backend running with `DEMO_MODE=true`, frontend running, Telegram open on your phone, Chrome (for voice). Log in, open **Reminders**, check every item in the status line says ok / ready / running, press **Reset demo** and confirm.

| Time | Click path | What to say |
| --- | --- | --- |
| 0:00 | Log in (`9876543210`, any 6 digits). **Home**. | Today's medicines and three warnings already waiting: Clarithromycin with Atorvastatin, Metformin written twice, LDL above target. |
| 0:30 | **Timeline**. Tap **മലയാളം** in the top bar. | Eight records in one thread. Every summary is also in Malayalam. |
| 0:50 | **Health**. | The sugar chart is built from stored lab values, not mock data. HbA1c fell from 9.1 to 7.2. |
| 1:10 | **Add**. Choose `BackEnd/test_docs/sunrise_prescription.png`, press **Analyse**. | Five stages. Two new warnings: a drug clash and a duplicate. Press **Turn on these reminders**: the phone buzzes in Telegram. |
| 1:50 | Still on **Add**. Press **Use sample hospital record**. | A hospital's FHIR file. "Imported 7 records", with a duplicate warning for Telmisartan. Importing it again adds nothing. |
| 2:20 | **Add**, choose `BackEnd/test_docs/lab_report.png`, **Analyse**. | A new HbA1c of 8.2 makes three rises in a row: "7.2, 7.6, 8.2. Show this to your doctor." Plain Python, no AI, no cause, no treatment. |
| 2:50 | **Sharing**, **Create share link**, **Open doctor console**. Press **Play demo conversation**. | Safety flags appear as the doctor speaks. Press **Stop and review**, then **Approve and send to patient** and confirm. |
| 3:30 | In the approved panel, switch English / മലയാളം and press **Read aloud**. Back in the patient app, **Timeline**: the visit is the first card. | Nothing reached the patient until the doctor approved. |
| 3:45 | **Reminders**, **Fire missed dose alert now**. | The family gets a Telegram message. |
| 4:00 | **Reset demo** (or leave it). | |

## Tests and checks

```bash
cd BackEnd
./venv/bin/python -W ignore scripts/test_trends.py -v        # trend alert rules
./venv/bin/python -W ignore scripts/test_fhir.py -v          # FHIR import, dedupe, bad input
./venv/bin/python -W ignore scripts/test_reminders.py -v     # reminder engine, fake clock
./venv/bin/python scripts/smoke.py                           # needs a running server with DEMO_MODE=true
./venv/bin/python scripts/security_sweep.py                  # needs a running server
```

`smoke.py` and `/api/demo/reset` wipe the demo patient's uploads, imports and visits in whatever database the server points at.

## Known limits

- **Telegram is the only reminder channel.** The "notify on this phone" toggle only asks for browser permission and saves the setting. Nothing is pushed to the browser.
- **Browser voice needs Chrome and internet.** Voice typing uses the browser's Web Speech API, which sends audio to a cloud service. Other browsers get the typed-line fallback.
- **Free hosting sleeps.** On a free tier the server stops after idle time, the first request takes a long time to wake it, and the reminder scheduler does not run while it sleeps, so doses in that window are never sent. Open the app a minute before a demo.
- **Gemini's free tier runs out.** Uploads that are not in `demo_cache/` fail with a plain error when every model returns 429. Summaries fall back to plain text if Groq fails.
- **Login is a demo.** Any 6-digit code works; no SMS is sent.
- **Not a medical device.** The checks cover a small list of common drugs and lab ranges. Always ask a doctor.
