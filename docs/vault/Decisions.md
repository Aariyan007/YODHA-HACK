---
tags: [decisions]
---
# Decisions

Back to [[Home]]. Why we built it this way.

| Decision | Why |
| --- | --- |
| Model proposes, code decides | A wrong or tricked model must not be able to change records or invent facts. |
| Safety checks in plain Python | Fast, free, testable, and they work when the AI is down. |
| Every write asks Yes or No, with a preview, then verifies | The person stays in control; no silent changes. |
| Medicine changes are L4: no tool exists | Only a doctor changes medicines. |
| Doctor sees a patient only via a one-time code and care link | Patient controls access and can revoke it. |
| Handwriting: two readings must agree | A guessed medicine name is worse than "unclear". |
| Doctor never sees "unclear handwriting" notes | Patient-only concern; avoids undermining trust in the record. |
| Cap in-flight requests instead of just adding workers | The stall was connection/thread starvation; more workers alone would not fix it. See [[Scalability]]. |
| One backend worker | It owns the scheduler; two would double-send reminders. See [[Roadmap]]. |
| Sans-serif (Inter) UI | Looks like professional healthcare software, not an editorial site. |
| Laya stays off | It failed its own accuracy gate on Malayalam; we trust the rules and say so. |
