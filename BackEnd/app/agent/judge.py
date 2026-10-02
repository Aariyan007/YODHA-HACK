"""Reply judge: a second, small model checks that every claim in the agent's reply is supported by the tool results.

It runs AFTER the code checks (numbers present, no diagnosis / medicine-advice wording) and can only REMOVE a reply, never add or
change words. If the judge is unavailable the reply stays: the deterministic checks already passed. The data cards from the tools
are always shown, so a removed reply never hides real data."""
from __future__ import annotations

import os

SYSTEM = """You are a strict fact checker for a health-record assistant.
You get TOOL_RESULTS (the only allowed source of facts) and a REPLY written for the patient.
Step 1: split the REPLY into its separate claims. Step 2: for each claim, say whether TOOL_RESULTS or the patient's own words state it.
A claim is UNSUPPORTED if it adds anything not in TOOL_RESULTS: an outcome or prediction ("will stay under control", "should improve"),
a reason, a purpose, a target or guideline, a diagnosis, a fact about a medicine, or advice to start, stop, skip or change a medicine or dose.
Politeness and offers to help ("ask your doctor", "let me know") are fine.
Reply JSON only: {"claims": [{"claim": "short quote", "supported": true|false}], "supported": true only if every claim is supported}"""

MIN_REPLY = 60      # a one-line acknowledgement is not worth a model call
MAX_EVIDENCE = 3500


def enabled() -> bool:
    return os.getenv("AGENT_JUDGE", "1") != "0"


def check(llm, evidence: str, reply: str) -> tuple[bool, list[str]]:
    """-> (supported, unsupported_quotes). Fails open: (True, []) when the judge cannot answer."""
    if not enabled() or len(reply) < MIN_REPLY:
        return True, []
    out = llm.judge(SYSTEM, f"TOOL_RESULTS:\n{evidence[:MAX_EVIDENCE]}\n\nREPLY:\n{reply}")
    if not isinstance(out, dict) or "supported" not in out:
        return True, []
    claims = [c for c in (out.get("claims") or []) if isinstance(c, dict)]
    bad = [str(c.get("claim"))[:80] for c in claims if c.get("supported") is False][:3]
    ok = out["supported"] is True and not bad  # one unsupported claim is enough, whatever the overall flag says
    return ok, bad
