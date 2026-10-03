---
tags: [architecture, flows]
---
# Request flows

Back to [[Architecture]].

## Sign in
1. Browser sends `POST /api/auth/login`.
2. nginx rate-limits it (10 per minute).
3. Backend checks the lockout (5 wrong tries for the same email and IP = 15 minutes).
4. Password checked against the scrypt hash. At most 3 hashes run at once ([[Scalability]]).
5. A JWT comes back (`sub` = patient id, role patient or doctor). The browser keeps it in localStorage.
6. Every later call sends `Authorization: Bearer ...`. A doctor token on a patient route is 401, and the reverse. A doctor sees a patient only through an active care link (otherwise 404).

## Upload a record
1. `POST /api/documents` checks size (10 MB), the real file type (magic bytes) and duplicates.
2. A job id is returned. The browser listens to `/api/jobs/{id}/events` (progress stream).
3. Background thread: Gemini extracts JSON (handwriting gets a second careful reading) -> Python checks (duplicates, allergies, interactions, lab ranges) -> Groq writes the summary and Malayalam -> save document, observations, medicines, alerts -> trends and whole-record risk check.
4. Results are cached by the file hash, so a re-upload is instant and costs no AI quota.

## A doctor visit
1. Doctor console starts a consultation with the share token.
2. Each spoken clip -> speech to text (silence and "thank you" ghost text filtered) -> drug-name correction (shown as heard -> corrected, never silent) -> Python flags -> a partial note every 3 lines.
3. Finalize: full note and visit classification (complaints, diagnoses, medicines, tests, advice) built in parallel. Code validates: every item must cite a real doctor line and share real words with it.
4. Approve: the doctor may remove items but cannot add any. Only then the visit reaches the patient timeline, reminders and Telegram.

## Reminders
APScheduler every 30 s (India time). A dose is claimed (key `medicine@HH:MM@date`) before it is sent, so a restart never double-sends. Also hourly nudges (max 5 per dose, none after 22:00), a missed-dose message to the family, refill and follow-up notices.

Related: [[Agent]], [[Data model]].
