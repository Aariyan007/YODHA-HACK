---
tags: [safety]
---
# Safety and privacy

Back to [[Home]].

- **AI never diagnoses and never advises on medicines.** It restates what a document or doctor said and flags things to show a doctor.
- **Nothing silent.** Writes need Yes or No. The medicine-change guard runs before the model.
- **Replies are checked** by code (numbers must exist in the results, no diagnosis wording) and by a second model that removes unsupported claims. See [[Agent]].
- **Role separation.** Patient and doctor tokens are not interchangeable. Fake or unlinked ids answer 404 so ids cannot be probed.
- **Doctors never see "handwriting unclear" notes.** Filtered from shares, the doctor view, the doctor agent and PDFs.
- **Files** are encrypted with AES-256-GCM, bound to the file and patient. Passwords use scrypt.
- **Secrets** never appear in logs, task results or audit. HTTP client loggers are forced to WARNING because they would log the Telegram URL.
- **Edge hardening** (Docker): rate limits, 11 MB upload cap, CSP and security headers, non-root containers, read-only backend filesystem, no published ports for the backend or Redis.
- **Handwriting:** a medicine is certain only if two readings agree, the name is legible and it is a known drug. Otherwise it is shown as unclear and never saved.
- **Data licences:** DDInter and one training set are non-commercial. The doctor directory is fictional.

Related: [[Known limits]], [[Judge Q and A]].
