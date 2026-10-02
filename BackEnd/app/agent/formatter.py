"""AgentResponseFormatter: tool results -> the structured blocks the Agent UI renders. Deterministic (no LLM), so every
number on screen comes from a record and carries evidence."""
from __future__ import annotations

from .planner import Plan
from .types import ToolResult, block

LEAD = {
    "latest_records": "Your latest records:", "search": "Records that match:", "medications": "Your current medicines:",
    "care_loop": "Today's doses:", "labs": "Your latest results:", "alerts": "What needs your attention:",
    "pdf": "Your PDF:", "brief": "Pre-visit brief:", "changes": "What changed:", "conflicts": "Records to verify:", "missing_info": "Possible gaps:", "consult_draft": "Draft visit note:", "medicine_change": "About your medicines:", "visit_prep": "Getting ready for your visit:", "multi_step": "Here is what I did:", "file_summary": "About this file:", "file_entities": "What the file contains:", "file_compare": "Compared with your thread:", "file_evidence": "Where it says that:",
    "find_doctor": "Doctors from the sample directory (not real clinics):", "sharing_status": "Sharing right now:",
}
DISCLAIMER = "This is information from your own records, not medical advice. Your doctor decides about treatment."


class AgentResponseFormatter:
    def format(self, plan: Plan, results: list[ToolResult]) -> dict:
        blocks: list[dict] = []
        evidence: list[dict] = []
        seen: set[str] = set()
        confirmation = None
        for r in results:
            if r.status == "needs_confirmation":
                confirmation = r.confirmation
            elif not r.ok and r.error and not r.blocks:
                blocks.append(block("error", text=r.error))
            blocks += r.blocks
            for e in r.evidence:
                k = f"{e.get('kind')}:{e.get('id')}"
                if k not in seen:
                    seen.add(k)
                    evidence.append(e)
        if plan.clarify and results:  # a standing note the person must see with the results (e.g. why a medicine change is not possible)
            blocks.insert(0, block("text", text=plan.clarify))
        lead = LEAD.get(plan.intent)
        if lead and blocks and blocks[0]["type"] != "text" and not plan.clarify:
            blocks.insert(0, block("text", text=lead))
        if not blocks:
            blocks = [block("text", text=plan.clarify or "I have nothing to show for that.")]
        return {"intent": plan.intent, "blocks": blocks, "evidence": evidence, "confirmation": confirmation,
                "disclaimer": DISCLAIMER if evidence else None}
