"""Agent tasks: durable, resumable jobs with a visible state.

queued -> planning -> running -> waiting_for_confirmation -> running -> completed | failed | cancelled

Quick plans run inline in the request. A plan with a slow step (a model reading a file) runs in a background thread with its
own DB session; the browser polls GET /api/agent/tasks/{id} for step-by-step progress. Every step's result is stored on the
task row, so a task that waits for the person's confirmation can be resumed by /confirm even after a restart.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import AgentTask, now
from .context import AgentContext
from .types import ToolResult

log = logging.getLogger("agent.tasks")
SESSION: Callable[[], Session] = SessionLocal  # tests point this at their in-memory database
STATES = ("queued", "planning", "running", "waiting_for_confirmation", "completed", "failed", "cancelled")
TERMINAL = ("completed", "failed", "cancelled")


def run_in_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


def result_to_dict(r: ToolResult) -> dict:
    return {"ok": r.ok, "status": r.status, "tool": r.tool, "blocks": r.blocks, "evidence": r.evidence, "error": r.error,
            "confirmation": r.confirmation}


def result_from_dict(d: dict) -> ToolResult:
    return ToolResult(d["ok"], d["status"], d["tool"], blocks=d.get("blocks", []), evidence=d.get("evidence", []),
                      error=d.get("error"), confirmation=d.get("confirmation"))


def create(ctx: AgentContext, intent: str, steps: list[dict]) -> AgentTask:
    t = AgentTask(user_id=ctx.actor_id, agent_type=ctx.agent_type, patient_id=ctx.patient_id, conversation_id=ctx.conversation_id,
                  intent=intent[:40], status="queued",
                  steps=[{"tool": s["tool"], "args": s["args"], "label": s["label"], "status": "queued"} for s in steps])
    ctx.db.add(t)
    ctx.db.flush()
    return t


def set_status(db: Session, t: AgentTask, status: str, error: str | None = None) -> None:
    assert status in STATES
    t.status, t.updated_at = status, now()
    if error is not None:
        t.error = error[:300]
    db.commit()


def set_step(db: Session, t: AgentTask, i: int, **fields) -> None:
    steps = [dict(s) for s in t.steps]  # a new list, so SQLAlchemy sees the JSON change
    steps[i].update(fields)
    t.steps, t.updated_at = steps, now()
    db.commit()


def add_step(db: Session, t: AgentTask, tool: str, label: str, status: str = "running") -> int:
    t.steps = [*t.steps, {"tool": tool, "args": {}, "label": label, "status": status}]
    t.updated_at = now()
    db.commit()
    return len(t.steps) - 1


def owned(db: Session, actor_id: str, role: str, task_id: str) -> AgentTask | None:
    return db.scalar(select(AgentTask).where(AgentTask.id == task_id, AgentTask.user_id == actor_id, AgentTask.agent_type == role))


def public(t: AgentTask) -> dict:
    """What the browser sees: state + compact steps (no stored tool results, no arguments)."""
    return {"taskId": t.id, "status": t.status, "intent": t.intent, "error": t.error,
            "steps": [{"tool": s["tool"], "label": s["label"], "status": s["status"]} for s in t.steps],
            "result": t.result if t.status in TERMINAL or t.status == "waiting_for_confirmation" else None}


def purge_old(days: int = 30) -> int:
    """Stored task results hold record text for the person's own convenience; drop them after `days`. The audit log stays."""
    from datetime import timedelta
    from sqlalchemy import delete
    with SESSION() as db:
        n = db.execute(delete(AgentTask).where(AgentTask.created_at < now() - timedelta(days=days))).rowcount or 0
        db.commit()
    return n
