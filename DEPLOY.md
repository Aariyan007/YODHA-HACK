# Deploying MediThread to Render (one service)

The API and the built web app run in one container (`deploy/render/Dockerfile`), so there is no CORS to set up and the upload
progress stream works. Postgres stays on Supabase. `render.yaml` describes everything.

## 1. Before you start
- The code must be on GitHub (Render builds from the repo): `git push origin main`.
- Keep your `.env` out of git (it already is). Render never reads it; you paste the values in step 3.
- Make a file-encryption key. **Save it somewhere safe: if it changes, stored files cannot be opened again.**
  `python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`

## 2. Create it
Render dashboard > New > Blueprint > pick this repo > Apply. It creates the `medithread` web service. There is no Redis: pending
confirmations and rate limits are kept in memory, so a restart forgets an unanswered confirmation (nothing else is lost).

## 3. Fill in the values it asks for
| Name | Value |
|---|---|
| `DATABASE_URL` | Your Supabase **session pooler** URL (`...pooler.supabase.com:5432`). The app switches to the transaction pooler itself |
| `FILE_ENC_KEY` | The key from step 1 |
| `GEMINI_API_KEY`, `GROQ_API_KEY`, `ELEVENLABS_API_KEY` | Your keys |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Optional: reminders |
| `ADMIN_EMAILS` | Emails allowed to open `/admin` |

`JWT_SECRET` is generated for you. `DEMO_MODE` is `false`: no demo login and no demo reset.

## 4. Check it
Open `https://<your-service>.onrender.com`. `/api/health/ready` should say `"ready": true`. Register a patient, upload a report,
ask the agent something.

## Limits of the free plan (fine for a demo)
- **It sleeps after about 15 minutes idle** and takes 30 to 60 seconds to wake. Telegram reminders only go out while it is awake. A
  free uptime pinger on `/api/health` keeps it up.
- **Files are not kept across restarts.** The encrypted vault and uploads live on the container's disk. A paid plan with a
  Render Disk mounted at `/app/vault` and `/app/uploads` keeps them. Database rows stay either way.
- **Free tier AI limits** (Gemini, Groq) are what you will hit first with many users. The agent falls back to rules when Groq is out.
- Not ready for real patients: Malayalam triage is rule-only, the doctor directory is sample data, and there has been no clinical or
  privacy review.
