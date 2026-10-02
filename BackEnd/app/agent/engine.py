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

import json

from . import loop, tasks
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
        self.llm = llm or default_llm()

    # ------------------------------------------------------------------ chat
    def chat(self, ctx: AgentContext, text: str) -> dict:
        conv = ctx.conversation_id = ctx.conversation_id or uuid.uuid4().hex[:12]
        history = self.memory.history(ctx.role, ctx.actor_id, conv)
        ctx.session = self.memory.session(ctx.role, ctx.actor_id, conv)
        guard = self.planner.guard(ctx.role, text)  # fixed answers that must hold whatever a model says (medicine changes, delivery)
        if guard is None and self.llm.available():
            started = self._agent_start(ctx, text, history, conv)
            if started is not None:
                return started
        plan = guard or self.planner.plan(ctx.role, text, history, ctx.file_id, ctx.session)
        if not plan.steps:  # a question back to the person, or nothing to do: no task needed
            out = self.formatter.format(plan, [])
            out.update(steps=[], conversationId=conv, planSource=plan.source, status="completed")
            self.memory.add_turn(ctx.role, ctx.actor_id, conv, text, plan.intent)
            return out
        specs = [REGISTRY.get(s.tool) for s in plan.steps]
        task = tasks.create(ctx, plan.intent, [{"tool": s.tool, "args": s.args, "label": _label(sp)} for s, sp in zip(plan.steps, specs)])
        task.result = {"userText": text[:300], "planSource": plan.source, "lead": plan.clarify}
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

    # ------------------------------------------------------------------ the agent loop (LLM chooses tools, code runs them)
    def _agent_start(self, ctx: AgentContext, text: str, history: list[dict], conv: str) -> dict | None:
        task = tasks.create(ctx, "agent", [])
        task.result = {"userText": text[:300], "planSource": "llm"}
        ctx.db.commit()
        if ctx.file_id:  # reading a file is slow: the whole loop runs in the background and the UI follows the steps
            snap = dict(role=ctx.role, actor_id=ctx.actor_id, actor_name=ctx.actor_name, patient_id=ctx.patient_id, scope=ctx.scope,
                        lang=ctx.lang, conversation_id=conv, file_id=ctx.file_id, request_id=ctx.request_id, session=dict(ctx.session))
            tid = task.id
            self.runner(lambda: self._agent_background(tid, snap, text, history))
            return {"taskId": tid, "status": "running", "intent": "agent", "conversationId": conv, "planSource": "llm",
                    "blocks": [block("progress", taskId=tid)], "steps": [], "evidence": [], "confirmation": None, "disclaimer": None}
        out = self._agent_loop(ctx, task, text, history, conv)
        if out is None:  # the model was unavailable or rate-limited before doing anything: let the rules answer instead
            ctx.db.delete(task)
            ctx.db.commit()
        return out

    def _agent_background(self, task_id: str, snap: dict, text: str, history: list[dict]) -> None:
        db = tasks.SESSION()
        try:
            task = db.get(tasks.AgentTask, task_id)
            ctx = AgentContext(db=db, **snap)
            out = self._agent_loop(ctx, task, text, history, snap["conversation_id"])
            if out is None:  # model gone: fall back to the rules, still inside this task
                plan = self.planner.plan(ctx.role, text, history, ctx.file_id, ctx.session)
                task.intent = plan.intent[:40]
                task.steps = [{"tool": s.tool, "args": s.args, "label": _label(REGISTRY.get(s.tool)), "status": "queued"} for s in plan.steps]
                db.commit()
                self._run(ctx, task, plan.intent, snap["conversation_id"], plan.source)
        except Exception as e:
            log.warning("agent task %s crashed: %s", task_id, type(e).__name__)
            try:
                db.rollback()
                tasks.set_status(db, db.get(tasks.AgentTask, task_id), "failed", "Something went wrong while working on that.")
            except Exception:
                pass
        finally:
            db.close()

    def _agent_loop(self, ctx: AgentContext, task, text: str, history: list[dict], conv: str) -> dict | None:
        specs = loop.pick_tools(REGISTRY, ctx.role, text, bool(ctx.file_id))
        by_fn = {loop.fn_name(s.name): s for s in specs}
        defs = loop.tool_defs(specs)
        msgs: list[dict] = [{"role": "system", "content": loop.system_prompt(ctx.role, ctx.session)}]
        for h in history[-4:]:
            msgs += [{"role": "user", "content": h["u"]}, {"role": "assistant", "content": f"(I looked at: {h['a']})"}]
        user = text + (f"\n(The person attached a file; its id is {ctx.file_id}. Read it with documents_extract first.)" if ctx.file_id else "")
        msgs.append({"role": "user", "content": user})
        tasks.set_status(ctx.db, task, "running")
        results, evidence_text, reply, ran, retried = [], text, "", False, False
        for _ in range(loop.MAX_ROUNDS):
            turn = self.llm.chat_tools(msgs, defs)
            if turn is None:
                if not ran:
                    return None
                break
            if not turn["tool_calls"]:
                reply = turn["content"]
                if not reply and not ran:
                    return None  # the model produced nothing usable: let the rules answer
                if reply and not retried and not loop.reply_ok(reply, evidence_text):
                    # one polite retry: the usual cause is an outside number (a guideline target) that is not in the record
                    retried = True
                    msgs += [{"role": "assistant", "content": reply},
                             {"role": "user", "content": "Rewrite your answer using only facts and numbers that appear in the tool results. No guidelines, targets, diagnoses or medicine advice."}]
                    continue
                break
            msgs.append({"role": "assistant", "content": turn["content"] or None,
                         "tool_calls": [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}} for c in turn["tool_calls"]]})
            stop = False
            for c in turn["tool_calls"]:
                spec = by_fn.get(c["name"])  # only tools offered for this request, for this role
                name = spec.name if spec else c["name"].replace("__", ".")
                try:
                    args = json.loads(c["arguments"] or "{}")
                    args = args if isinstance(args, dict) else {}
                except ValueError:
                    args = {}
                i = tasks.add_step(ctx.db, task, name, _label(spec) if spec else name)
                r = self.executor.run(ctx, name, args) if spec else self.executor.run(ctx, "unknown.tool", {})
                ctx.db.commit()
                ran = True
                results.append(r)
                step = {"status": r.status, "result": tasks.result_to_dict(r)}
                if r.status == "needs_confirmation":
                    step["confirmationId"] = r.confirmation["id"]
                    stop = True
                tasks.set_step(ctx.db, task, i, **step)
                if r.ok and isinstance(r.data, dict) and r.data.get("consultationId"):
                    self.memory.set_session(ctx.role, ctx.actor_id, conv, last_consultation=r.data["consultationId"])
                shown = loop.view(name, r.blocks, r.error)
                evidence_text += " " + shown
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": shown if r.status != "needs_confirmation" else "waiting for the person to confirm"})
            if stop:
                break
        cards, ev, conf = loop.to_blocks(results)
        if conf:
            reply = loop.fixed_reply(conf)
        elif not loop.reply_ok(reply, evidence_text):
            reply = ""  # unsafe or unsupported wording is dropped; the real data cards below still show
        blocks = ([block("text", text=reply)] if reply else []) + cards
        if not blocks:
            blocks = [block("text", text="I could not put an answer together. Please try asking another way.")]
        failed = [r for r in results if not r.ok and r.status != "needs_confirmation"]
        status = "waiting_for_confirmation" if conf else "failed" if (failed and len(failed) == len(results) and results) else "completed"
        out = {"taskId": task.id, "status": status, "intent": "agent", "conversationId": conv, "planSource": "llm", "blocks": blocks,
               "evidence": ev, "confirmation": conf, "disclaimer": None if not ev else "This is information from your own records, not medical advice. Your doctor decides about treatment.",
               "steps": [{"tool": s["tool"], "status": s["status"]} for s in task.steps]}
        task.result = {**(task.result or {}), **{k: out[k] for k in ("blocks", "evidence", "confirmation", "disclaimer", "steps")}}
        tasks.set_status(ctx.db, task, status if status != "failed" else "failed", None)
        if status != "waiting_for_confirmation":
            self.memory.add_turn(ctx.role, ctx.actor_id, conv, text, ", ".join(dict.fromkeys(r.tool for r in results)) or "chat")
        return out

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
            if r.ok and isinstance(r.data, dict) and r.data.get("consultationId"):
                self.memory.set_session(ctx.role, ctx.actor_id, conv, last_consultation=r.data["consultationId"])
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
        out = self.formatter.format(Plan(intent, clarify=(task.result or {}).get("lead")), results)
        out.update(taskId=task.id, status=task.status, conversationId=conv, planSource=source,
                   steps=[{"tool": s["tool"], "status": s["status"]} for s in task.steps])
        if task.status == "cancelled":
            out["blocks"].append(block("text", text="Stopped."))
        task.result = {**(task.result or {}), **{k: out[k] for k in ("blocks", "evidence", "confirmation", "disclaimer", "steps")}}
        ctx.db.commit()
        if task.status in tasks.TERMINAL:
            # Memory holds the person's own words and the intent label, never text that came out of a record or a document,
            # so a document cannot plant instructions that the planner later reads as conversation history.
            self.memory.add_turn(ctx.role, ctx.actor_id, conv, (task.result or {}).get("userText", ""), intent)
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
