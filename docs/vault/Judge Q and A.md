---
tags: [judges]
---
# Judge Q and A

Back to [[Home]].

**Can the AI make a mistake?** Yes, so it never decides. Safety checks are plain code and every AI claim is checked against the data. [[Agent]]

**What if the AI is down or rate-limited?** Rules-only versions still work: danger checks, the emergency banner, interactions and reminders do not depend on AI. [[AI services]]

**Can a doctor see everything?** Only after the patient shares a one-time code, only that patient, and the patient can cut access immediately. [[Safety and privacy]]

**How does it scale?** We load-tested 100 simultaneous users, found a real stall, fixed it (0 errors, about 60 req/s). Next: paid AI tiers, a job queue, a separate reminder service. [[Scalability]] [[Roadmap]]

**Why not let the AI write to the database?** Because a wrong or tricked model could change a record. Tools are registered, checked, confirmed and audited. [[Decisions]]

**How do you stop it inventing numbers?** Code checks that each number in a reply exists in the tool results, a second model removes unsupported claims, and extraction keeps a value only if it is found in the document text with page, line and quote. [[Agent]]

**What about handwriting?** Two readings; a medicine counts only if both agree and it is a known drug. Otherwise it shows as unclear and is never saved. [[Safety and privacy]]

**What does it cost to run?** We meter tokens by feature, cut the assistant cost about 3 to 4 times per question, and limit use per person per day. [[Token optimisation]]

**Is it a medical device?** No. It checks a small list of drugs and ranges and always says to ask a doctor. [[Known limits]]
