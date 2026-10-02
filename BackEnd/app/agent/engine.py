"""AgentEngine: Intent -> Context -> Plan -> Tools -> Evidence -> Action -> Verification -> Result.

One engine, two agents (patient, doctor). The difference is only the context built by the router and the tools the
registry exposes for that role. The model never touches the DB: it can only propose registered tool calls.
"""
from __future__ import annotations

import os
import uuid

from .executor import AgentExecutor
from .context import AgentContext
from .formatter import AgentResponseFormatter
from .llm import GroqLLM, LLMService, NullLLM
from .memory import AgentMemory
from .planner import AgentPlanner
from .registry import REGISTRY
from .types import ToolResult
from . import tools  # noqa: F401  (registers tools)


def default_llm() -> LLMService:
    return GroqLLM() if os.getenv("GROQ_API_KEY") else NullLLM()


class AgentEngine:
    def __init__(self, llm: LLMService | None = None, executor: AgentExecutor | None = None, memory: AgentMemory | None = None):
        self.executor = executor or AgentExecutor()
        self.memory = memory or AgentMemory()
        self.planner = AgentPlanner(REGISTRY, llm or default_llm())
        self.formatter = AgentResponseFormatter()

    def chat(self, ctx: AgentContext, text: str) -> dict:
        conv = ctx.conversation_id = ctx.conversation_id or uuid.uuid4().hex[:12]
        history = self.memory.history(ctx.role, ctx.actor_id, conv)
        plan = self.planner.plan(ctx.role, text, history, ctx.file_id)
        results: list[ToolResult] = []
        for step in plan.steps:
            r = self.executor.run(ctx, step.tool, step.args)
            results.append(r)
            if r.status == "needs_confirmation":
                break  # nothing after a pending write may run until the person answers
            if not r.ok:
                break  # later steps depend on earlier ones (read before summarise), so stop at the first failure
        out = self.formatter.format(plan, results)
        out["steps"] = [{"tool": r.tool, "status": r.status} for r in results]  # compact activity log
        out["conversationId"] = conv
        out["planSource"] = plan.source
        first_text = next((b.get("text") for b in out["blocks"] if b["type"] == "text"), "")
        self.memory.add_turn(ctx.role, ctx.actor_id, conv, text, f"{plan.intent}: {first_text or ''}")
        return out

    def confirm(self, ctx: AgentContext, cid: str, approve: bool) -> dict:
        r = self.executor.confirm(ctx, cid, approve)
        out = self.formatter.format(_Intent("confirmed"), [r])
        out["steps"] = [{"tool": r.tool, "status": r.status}]
        return out


class _Intent:
    def __init__(self, intent: str):
        self.intent, self.clarify = intent, None
