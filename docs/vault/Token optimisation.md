---
tags: [ai, cost]
---
# Token optimisation

Back to [[Home]]. The free Groq tier allows 8,000 tokens per minute and 200,000 per day, per model.

## Measured baseline
One assistant call sent about 2,900 tokens (instructions about 1,200 + 34 tool definitions about 2,600 characters / 4), and one question made about 3 calls (about 8,800 tokens).

## What changed
- A token counter by feature and day (`app/tokens.py`, shown as `tokensToday` on `/admin`). Numbers only.
- Shorter prompt and tool list. Min/max values are no longer sent (the code validates them).
- The tool list is not re-sent after round 1 unless the request has several parts, or a tool that usually leads to another step was used.
- History is 3 turns, capped at 300 and 400 characters.
- Tool arguments the model invents are dropped (this also fixed a failure on "doses today").

## Result
Two simple questions: 2 calls, 5,112 tokens in total. About 3 to 4 times cheaper per question.

## Not done
- Visit-note calls rebuild the partial note from all lines every 3 lines, so long visits cost more and more.
- The health review sends the whole record.
- Matching tools to the request (it hid tools on casual wording before).

Related: [[Agent]], [[AI services]], [[Scalability]].
