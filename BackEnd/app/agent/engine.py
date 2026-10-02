"""AgentEngine: Intent -> Context -> Plan -> Tools -> Evidence -> Action -> Verification -> Result.

One engine, two agents (patient, doctor). The difference is only the context built by the router and the tools the
registry exposes for that role. The model never touches the DB: it can only propose registered tool calls.

Every multi-step request is an AgentTask. Steps run in order and stop at the first failure or at the first step that
needs the person's confirmation; /confirm resumes the rest.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Callable

from sqlalchemy.orm import Session

from . import tasks
from .context import AgentContext
from .executor import AgentExecutor
from .formatter import AgentResponseFormatter
from .llm import GroqLLM, LLMService, NullLLM
from .memory import AgentMemory
from .planner import AgentPlanner, Plan
from .registry import REGISTRY
from .types import block
from . import tools  # noqa: F401  (registers tools)

log = logging.getLogger("agent.engine")


def default_llm() -> LLMService:
    return GroqLLM() if os.getenv("GROQ_API_KEY") else NullLLM()


def _label(spec) -> str:
    return spec.description.split(".")[0][:70]


class AgentEngine:
    def __init__(self, llm: LLMService | None = None, executor: AgentExecutor | None = None, memory: AgentMemory | None = None,
                 runner: Callable[[Callable[[], None]], None] | None = None):
        self.executor = executor or AgentExecutor()
        self.memory = memory or AgentMemory()
        self.planner = AgentPlanner(REGISTRY, llm or default_llm())
        self.formatter = AgentResponseFormatter()
        self.runner = runner or tasks.run_in_thread

    # ------------------------------------------------------------------ chat
    def chat(self, ctx: AgentContext, text: str) -> dict:
        conv = ctx.conversation_id = ctx.conversation_id or uuid.uuid4().hex[:12]
        history = self.memory.history(ctx.role, ctx.actor_id, conv)
        plan = self.planner.plan(ctx.role, text, history, ctx.file_id)
        if not plan.steps:  # a question back to the person, or nothing to do: no task needed
            out = self.formatter.format(plan, [])
            out.update(steps=[], conversationId=conv, planSource=plan.source, status="completed")
            self.memory.add_turn(ctx.role, ctx.actor_id, conv, text, f"{plan.intent}: {out['blocks'][0].get('text', '')}")
            return out
        specs = [REGISTRY.get(s.tool) for s in plan.steps]
        task = tasks.create(ctx, plan.intent, [{"tool": s.tool, "args": s.args, "label": _label(sp)} for s, sp in zip(plan.steps, specs)])
        task.result = {"userText": text[:300], "planSource": plan.source}
        ctx.db.commit()
        if any(sp and sp.slow for sp in specs):
            snap = dict(role=ctx.role, actor_id=ctx.actor_id, actor_name=ctx.actor_name, patient_id=ctx.patient_id, scope=ctx.scope,
                        lang=ctx.lang, conversation_id=conv, file_id=ctx.file_id, request_id=ctx.request_id)
            tid = task.id
            self.runner(lambda: self._background(tid, snap))
            return {"taskId": tid, "status": "running", "intent": plan.intent, "conversationId": conv, "planSource": plan.source,
                    "blocks": [block("progress", taskId=tid)], "steps": [{"tool": s["tool"], "status": s["status"]} for s in task.steps],
                    "evidence": [], "confirmation": None, "disclaimer": None}
        return self._run(ctx, task, plan.intent, conv, plan.source)

    def _background(self, task_id: str, snap: dict) -> None:
        db = tasks.SESSION()
        try:
            task = db.get(tasks.AgentTask, task_id)
            ctx = AgentContext(db=db, **snap)
            self._run(ctx, task, task.intent, snap["conversation_id"], (task.result or {}).get("planSource", "rules"))
        except Exception as e:
            log.warning("background task %s crashed: %s", task_id, type(e).__name__)
            try:
                db.rollback()
                t = db.get(tasks.AgentTask, task_id)
                tasks.set_status(db, t, "failed", "Something went wrong while working on that.")
            except Exception:
                pass
        finally:
            db.close()

    # ------------------------------------------------------------------ run / resume
    def _run(self, ctx: AgentContext, task, intent: str, conv: str, source: str) -> dict:
        """Run the task's queued steps from the first unfinished one; return the formatted outcome."""
        tasks.set_status(ctx.db, task, "running")
        for i, s in enumerate(task.steps):
            if s["status"] != "queued":
                continue
            ctx.db.refresh(task)
            if task.status == "cancelled":
                return self._finish(ctx, task, intent, conv, source)
            tasks.set_step(ctx.db, task, i, status="running")
            r = self.executor.run(ctx, s["tool"], s["args"])
            ctx.db.commit()  # audit rows
            step = {"status": r.status if r.status in ("ok", "failed", "denied", "invalid", "unknown_tool", "needs_confirmation") else "failed",
                    "result": tasks.result_to_dict(r)}
            if r.status == "needs_confirmation":
                step["confirmationId"] = r.confirmation["id"]
            tasks.set_step(ctx.db, task, i, **step)
            if r.status == "needs_confirmation":
                tasks.set_status(ctx.db, task, "waiting_for_confirmation")
                return self._finish(ctx, task, intent, conv, source)
            if not r.ok:
                tasks.set_status(ctx.db, task, "failed", r.error)
                return self._finish(ctx, task, intent, conv, source)
        tasks.set_status(ctx.db, task, "completed")
        return self._finish(ctx, task, intent, conv, source)

    def _finish(self, ctx: AgentContext, task, intent: str, conv: str, source: str) -> dict:
        results = [tasks.result_from_dict(s["result"]) for s in task.steps if s.get("result")]
        out = self.formatter.format(Plan(intent), results)
        out.update(taskId=task.id, status=task.status, conversationId=conv, planSource=source,
                   steps=[{"tool": s["tool"], "status": s["status"]} for s in task.steps])
        if task.status == "cancelled":
            out["blocks"].append(block("text", text="Stopped."))
        task.result = {**(task.result or {}), **{k: out[k] for k in ("blocks", "evidence", "confirmation", "disclaimer", "steps")}}
        ctx.db.commit()
        if task.status in tasks.TERMINAL:
            first = next((b.get("text") for b in out["blocks"] if b["type"] == "text"), "")
            user_text = (task.result or {}).get("userText", "")
            self.memory.add_turn(ctx.role, ctx.actor_id, conv, user_text, f"{intent}: {first or ''}")
        return out

    # ------------------------------------------------------------------ confirmation
    def confirm(self, ctx: AgentContext, cid: str, approve: bool) -> dict:
        task = self._task_waiting_on(ctx, cid)
        r = self.executor.confirm(ctx, cid, approve)
        ctx.db.commit()
        if task is None:  # a confirmation that did not come from a task (direct tool call)
            out = self.formatter.format(Plan("confirmed"), [r])
            out["steps"] = [{"tool": r.tool, "status": r.status}]
            return out
        i = next(n for n, s in enumerate(task.steps) if s.get("confirmationId") == cid)
        conv = ctx.conversation_id = task.conversation_id
        intent = task.intent
        source = (task.result or {}).get("planSource", "rules")
        if r.status in ("invalid", "denied"):  # expired, not yours, or changed: the task cannot go on
            tasks.set_step(ctx.db, task, i, status="failed", result=tasks.result_to_dict(r), confirmationId=None)
            tasks.set_status(ctx.db, task, "failed", r.error)
            return self._finish(ctx, task, intent, conv, source)
        if r.status == "declined" or not approve:
            tasks.set_step(ctx.db, task, i, status="declined", result=tasks.result_to_dict(r), confirmationId=None)
            tasks.set_status(ctx.db, task, "cancelled")
            return self._finish(ctx, task, intent, conv, source)
        tasks.set_step(ctx.db, task, i, status="ok" if r.ok else "failed", result=tasks.result_to_dict(r), confirmationId=None)
        if not r.ok:
            tasks.set_status(ctx.db, task, "failed", r.error)
            return self._finish(ctx, task, intent, conv, source)
        return self._run(ctx, task, intent, conv, source)  # continue with the steps after the confirmed one

    @staticmethod
    def _task_waiting_on(ctx: AgentContext, cid: str):
        from sqlalchemy import select
        for t in ctx.db.scalars(select(tasks.AgentTask).where(tasks.AgentTask.user_id == ctx.actor_id, tasks.AgentTask.agent_type == ctx.role,
                                                              tasks.AgentTask.status == "waiting_for_confirmation")):
            if any(s.get("confirmationId") == cid for s in t.steps):
                return t
        return None

    # ------------------------------------------------------------------ cancel
    def cancel(self, ctx: AgentContext, task_id: str) -> dict | None:
        t = tasks.owned(ctx.db, ctx.actor_id, ctx.role, task_id)
        if t is None:
            return None
        if t.status not in tasks.TERMINAL:
            tasks.set_status(ctx.db, t, "cancelled")  # a running task notices between steps
        return tasks.public(t)
