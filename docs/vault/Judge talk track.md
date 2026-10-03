---
tags: [judges]
---
# Judge talk track

Back to [[Home]]. Say it in simple words.

**One line:** "The backend is the safe brain. AI reads and explains, but plain code decides what is true and what is allowed."

## 1. What it does (30 s)
- Reads a photo or PDF, explains it in English and Malayalam.
- Safety checks are normal code: duplicate medicines, allergy clashes, dangerous drug pairs, danger signs in the whole record.
- Telegram reminders that never double-send, and tell the family about missed doses.
- A doctor speaks the visit and gets a draft note. Nothing reaches the patient until the doctor approves.
- Patients and doctors have separate logins. Doctor access needs a one-time code, and the patient can remove it any time.

## 2. The Agent (45 s)
- An assistant that can answer and act ("share my reports for 2 hours").
- The AI never touches the database. It can only ask for one of 46 tools. Code checks who asks, what is allowed, and the data. Anything that saves or shares asks Yes or No.
- Every number in a reply must be in the patient's data, and a second AI removes claims the data does not back.
- It never diagnoses or advises on medicines. See [[Agent]].

## 3. Privacy (20 s)
Encrypted files, hashed passwords, strict role separation, handwriting "unclear" notes for the patient only. See [[Safety and privacy]].

## 4. Scalability (30 s)
We tested 100 people at once. First: timeouts and many errors. We found why and fixed it. Now: 0 errors, about 60 requests per second, pages in about a second. Plus daily limits per person and caching to protect the free AI quota. See [[Scalability]].

## 5. Be honest
One backend process today; free AI quotas; Laya off for Malayalam; sample doctor data; the free host sleeps. See [[Known limits]].
