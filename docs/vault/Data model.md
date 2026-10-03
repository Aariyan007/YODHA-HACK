---
tags: [data]
---
# Data model

Back to [[Architecture]].

| Table | Holds |
| --- | --- |
| users, patients | login identity (patient or doctor) and the profile |
| documents | timeline cards: lab, prescription, consultation, visit, scan; summaries EN and ML; extracted items; source lines |
| observations | every lab and vital value with code, unit, range, source |
| medicines, reminders, sent_doses, sent_notices, reminder_settings | prescriptions, dose times, send tracking, preferences |
| alerts | open warnings: interaction, duplicate, clash, allergy, lab, trend, risk, handwriting |
| share_links, invite_codes, care_links | QR links, one-time doctor codes, active doctor access |
| consultations | transcript, flags, note, classification |
| agent_tasks, agent_files, agent_audit | agent work, encrypted file records, audit trail |
| ai_decisions | Laya decisions (hash of the input, never the text) |

New nullable columns are added automatically at startup. See [[Request flows]].
