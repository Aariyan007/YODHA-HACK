# MediThread — YODHA 2.0 hackathon brief

24 hours. Builder is a beginner: explain each step in one short line, run commands, fix errors.

## Idea

Two connected apps, one backend.

1. Patient app (React, in /Frontend): patient uploads a photo of a prescription or lab report. AI reads it, puts it on a timeline, explains it in simple English and Malayalam, warns about medicine clashes and duplicates, makes reminders, sends a Telegram message.
2. Doctor console: doctor scans patient QR, sees history, records visit. AI writes a SOAP note, flags, and follow-up questions. Doctor approves. Note appears on the patient timeline.

AI never diagnoses. Doctor approves everything. No paid services.

## Folders

- /BackEnd: empty, to build
- /Frontend: Vite + React patient app (built by Claude, since the folder was empty). src/api/client.js + src/data/mockData.js define the API contract
- .env in project root: do not print, do not commit

Keys in .env: GEMINI_API_KEY, GROQ_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DATABASE_URL (Supabase Postgres), REDIS_URL, JWT_SECRET.

## Tech

- FastAPI + SQLAlchemy + python-dotenv, venv in /BackEnd/venv
- Images: Gemini via google-genai package, model gemini-3.8-flash (2.5-flash retired for new users; retry on 503)
- Text (summaries, Malayalam, SOAP): Groq, model openai/gpt-oss-120b (llama-3.3-70b-versatile no longer on Groq)
- No paid APIs. Drug clashes = hardcoded dangerous-pairs dict (~30 pairs, e.g. clarithromycin+atorvastatin, warfarin+aspirin), OpenFDA optional backup. Brand duplicates (Glycomet = metformin) via small brand-to-generic dict.
- Lab status (good/watch/alert) = plain Python threshold rules, no AI.
- Redis optional: if unreachable, fall back to in-memory dicts.
- If Supabase connection fails, fall back to local SQLite and tell the user.

## Contract

Frontend/src/api/client.js is the source of truth. Every endpoint returns the exact JSON shape that mockData.js and client.js use. All routes start with /api (Vite proxies /api to localhost:8000). Enable CORS.

## Phase 1 (do only this, then stop and report)

1. Create venv, install: fastapi uvicorn[standard] sqlalchemy psycopg2-binary python-multipart redis python-dotenv pydantic httpx python-jose[cryptography] google-genai groq Pillow. Save requirements.txt.
2. Folders: app/{main,database,models,schemas,auth,seed}.py, app/routers/{auth,patients,shares}.py, ai/ (empty files for now).
3. models.py tables: Patient, Document, Medicine, Observation, Alert, Consultation, ShareLink, AccessLog.
4. seed.py: load demo patient Ammini Varghese with her 8 timeline records, 3 medicines, 3 alerts, conditions, HbA1c history, family, access log, taken from mockData.js. Run on startup if DB is empty.
5. Auth: POST /api/auth/otp/request and /verify. Any 6-digit OTP works in demo. Return JWT + profile exactly like the mock.
6. Patient GET endpoints from client.js: timeline, alerts, insights, medicines, reminders, POST reminders/{key}/taken, access-log, family.
7. Shares: POST /api/shares and GET /api/shares/{token}/snapshot (expiry check, write AccessLog).
8. GET /health.
9. Test Gemini and Groq keys with one tiny call each; report pass or fail. Do not print keys.
10. Start uvicorn, curl /health and the login + timeline endpoints, show results.

## Rules

Never print or commit .env. Ask before anything that costs money. Commit to git after each working step with a short message.
