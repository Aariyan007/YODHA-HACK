"""AgentAuditLogger: one AgentAudit row per tool call. Stores ids and outcomes, never record text or secrets."""
from __future__ import annotations

import logging

from ..models import AgentAudit
from .context import AgentContext
from .types import ToolSpec

log = logging.getLogger("agent.audit")


class AgentAuditLogger:
    def record(self, ctx: AgentContext, spec: ToolSpec | None, tool: str, status: str, *, confirmed: bool = False,
               target: str | None = None, result_ref: str | None = None, detail: str | None = None) -> None:
        try:
            ctx.db.add(AgentAudit(
                actor_id=ctx.actor_id, actor_role=ctx.role, agent_type=ctx.agent_type, patient_id=ctx.patient_id,
                request_id=ctx.request_id, tool=tool[:60], category=(spec.audit_category if spec else "unknown")[:30],
                level=spec.level if spec else 0, target=(target or None) and str(target)[:80], status=status,
                confirmed=confirmed, result_ref=(result_ref or None) and str(result_ref)[:80],
                detail=(detail or None) and detail[:300],
            ))
            ctx.db.flush()
        except Exception as e:  # an audit failure must not break the read, but it must be visible in the logs
            log.warning("audit write failed: %s", type(e).__name__)
