---
tags: [limits]
---
# Known limits

Back to [[Home]]. Say these first; judges respect honesty.

- Throughput tops out near 100 requests per second because the database is remote (Supabase over the internet); more API copies past 3 do not help. See [[Scalability]].
- Free AI quotas (Groq, Gemini) run out long before the servers do. See [[Token optimisation]].
- Laya triage failed its own gate on Malayalam, so it is off and rules run. See [[AI services]].
- Doctor directory is fictional sample data.
- Free hosting sleeps when idle, so reminders pause. No Redis there, so limits and caches are per process. See [[Deployment]].
- Telegram is the only reminder channel.
- No email check or password reset.
- PDFs are English only.
- Not a medical device.
