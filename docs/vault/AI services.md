---
tags: [ai]
---
# AI services

Back to [[Architecture]].

| Job | Service | If it fails |
| --- | --- | --- |
| Read a document | Gemini (a list of models, falls through on quota) | plain error, cached results still replay |
| Summaries, Malayalam | Groq `openai/gpt-oss-120b` | plain-text summary |
| Agent tool loop | Groq, native function calling | rule planner answers |
| Reply judge | Groq `gpt-oss-20b` (own quota) | reply stays (code checks already passed) |
| Visit note, classification | Groq (+ fallback model) | cautious rule extraction, the review screen says so |
| Speech to text | ElevenLabs Scribe, then Groq Whisper | browser speech recognition |
| Handwriting | Gemini twice + optional TrOCR service | medicines shown as unclear |
| Drug interactions | DDInter dataset (local) | no alert for unknown pairs |
| Side effects | openFDA labels, quotes verified | honest "not found" |
| Triage urgency | rules first, optional Laya classifier | rules only |

**Laya** failed its own accuracy gate (Malayalam urgency 0.21), so it is switched off and the rules run instead. We report that honestly.

Related: [[Agent]], [[Token optimisation]], [[Known limits]].
