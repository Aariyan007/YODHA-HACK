"""AgentExecutor: the single door a tool call goes through.

  unknown tool? -> arguments valid? -> permission? -> confirmation needed? -> handler -> verify -> audit

The LLM never touches the DB. It names a registered tool with arguments; this module decides whether it runs.
L3 tools park a pending action in the store and return `needs_confirmation`; only `confirm()` can run them, and only
for the same actor, patient, tool and arguments that were shown to the person.
L4 is never executed: such tools may only explain, draft, prepare or flag, so none is registered with a write handler.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid

from .. import store
from .audit import AgentAuditLogger
from .context import AgentContext
from .permissions import AgentPermissionManager
from .registry import REGISTRY, AgentToolRegistry
from .types import ToolResult, block
from .validate import check

log = logging.getLogger("agent.exec")
PENDING_TTL = 10 * 60


def _args_hash(args: dict) -> str:
    return hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()[:16]


class AgentExecutor:
    def __init__(self, registry: AgentToolRegistry = REGISTRY, permissions: AgentPermissionManager | None = None,
                 audit: AgentAuditLogger | None = None):
        self.registry = registry
        self.permissions = permissions or AgentPermissionManager()
        self.audit = audit or AgentAuditLogger()

    def run(self, ctx: AgentContext, name: str, args: dict | None, confirmed: bool = False) -> ToolResult:
        args = args or {}
        spec = self.registry.get(name)
        if spec is None or ctx.role not in spec.roles:
            self.audit.record(ctx, None, name, "denied", detail="unknown tool")
            return ToolResult(False, "unknown_tool", name, error="That action is not available.")
        if err := check(spec.input_schema, args):
            self.audit.record(ctx, spec, name, "invalid", detail=err)
            return ToolResult(False, "invalid", name, error=err)
        ok, why = self.permissions.check(ctx, spec)
        if not ok:
            self.audit.record(ctx, spec, name, "denied", detail=why)
            return ToolResult(False, "denied", name, error=why, blocks=[block("warning", text=why)])
        if spec.level >= 4:  # L4 is never executed by the agent
            self.audit.record(ctx, spec, name, "denied", detail="L4 not executable")
            return ToolResult(False, "denied", name, error="This needs your doctor. I can only explain or prepare it.")
        if (spec.confirmation_required or spec.level >= 3) and not confirmed:
            return self._park(ctx, spec, name, args)
        try:
            out = spec.handler(ctx, args) or {}
            if spec.verify is not None and not spec.verify(ctx, args, out):
                self.audit.record(ctx, spec, name, "failed", confirmed=confirmed, detail="verification failed")
                return ToolResult(False, "failed", name, error="I could not confirm that this worked, so I did not report it as done.")
        except _ToolError as e:
            self.audit.record(ctx, spec, name, "failed", confirmed=confirmed, detail=str(e))
            return ToolResult(False, "failed", name, error=str(e), blocks=[block("error", text=str(e))])
        except Exception as e:  # handler bug: log the type only (messages can hold record text), tell the person plainly
            log.warning("tool %s failed: %s", name, type(e).__name__)
            self.audit.record(ctx, spec, name, "failed", confirmed=confirmed, detail=type(e).__name__)
            return ToolResult(False, "failed", name, error="Something went wrong with that step.",
                              blocks=[block("error", text="Something went wrong with that step.")])
        self.audit.record(ctx, spec, name, "ok", confirmed=confirmed, target=out.get("target"), result_ref=out.get("ref"))
        return ToolResult(True, "ok", name, data=out.get("data"), blocks=out.get("blocks", []), evidence=out.get("evidence", []))

    # ---- confirmation
    def _park(self, ctx: AgentContext, spec, name: str, args: dict) -> ToolResult:
        cid = uuid.uuid4().hex[:16]
        try:
            preview = spec.preview(ctx, args) if spec.preview else None  # what exactly will change, in words
        except _ToolError as e:  # nothing sensible to confirm (not found, ambiguous): say so instead of asking
            self.audit.record(ctx, spec, name, "failed", detail=str(e))
            return ToolResult(False, "failed", name, error=str(e), blocks=[block("error", text=str(e))])
        except Exception:
            preview = None
        pending = {"actor": ctx.actor_id, "role": ctx.role, "patient": ctx.patient_id, "tool": name, "args": args,
                   "hash": _args_hash(args)}
        store.set_value(f"agent:confirm:{cid}", json.dumps(pending, default=str), ttl=PENDING_TTL)
        self.audit.record(ctx, spec, name, "needs_confirmation", detail=_args_hash(args))
        conf = {"id": cid, "tool": name, "level": spec.level, "description": spec.description, "preview": preview}
        return ToolResult(False, "needs_confirmation", name, confirmation=conf,
                          blocks=[block("confirmation", id=cid, tool=name, title=spec.description, preview=preview, level=spec.level)])

    def confirm(self, ctx: AgentContext, cid: str, approve: bool) -> ToolResult:
        raw = store.get_value(f"agent:confirm:{cid}")
        if raw is None:
            return ToolResult(False, "invalid", "confirm", error="That confirmation has expired. Please ask again.")
        pending = json.loads(raw)
        if pending["actor"] != ctx.actor_id or pending["role"] != ctx.role or pending["patient"] != ctx.patient_id:
            self.audit.record(ctx, None, pending["tool"], "denied", detail="confirmation owner mismatch")
            return ToolResult(False, "denied", "confirm", error="That confirmation is not yours.")
        store.delete(f"agent:confirm:{cid}")  # single use, whatever the answer
        spec = self.registry.get(pending["tool"])
        if not approve:
            self.audit.record(ctx, spec, pending["tool"], "declined")
            return ToolResult(True, "declined", pending["tool"], blocks=[block("text", text="Okay, I did not do that.")])
        if _args_hash(pending["args"]) != pending["hash"]:
            return ToolResult(False, "invalid", "confirm", error="The request changed. Please ask again.")
        return self.run(ctx, pending["tool"], pending["args"], confirmed=True)


class _ToolError(Exception):
    """Raise from a handler for an expected, plain-language failure (not found, bad input)."""


ToolError = _ToolError
