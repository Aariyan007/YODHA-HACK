---
tags: [demo]
---
# Demo script

Back to [[Home]]. About 4 minutes.

1. **Sign in** (or the demo patient). Home shows today's medicines and warnings.
2. **Health Thread**: every record in date order; toggle Malayalam.
3. **Add**: upload a prescription -> five stages, new warnings -> turn on reminders (the phone buzzes in Telegram).
4. **Hospital import**: sample FHIR file; importing again adds nothing.
5. **Lab report** with a rising value -> "7.2, 7.6, 8.2. Show this to your doctor." (plain Python, no AI)
6. **Sharing** -> link or QR -> doctor console -> play the demo conversation -> review -> approve -> back in the patient app the visit is first.
7. **Agent**: "any tablets I missed today?", "share my sugar reports for 2 hours" (asks Yes or No), "how do I upload a report?" (shows the steps on screen).
8. **Tour** button: the guided tour and the auto-playing demo.
9. Mention [[Scalability]] numbers if asked.

Keep `BackEnd/demo_cache/` (instant replays) and have the offline build ready (`npm run build:single`). See [[Frontend]].
