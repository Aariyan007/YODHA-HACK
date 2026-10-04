"""Operator view: how the agents are used and whether they're healthy. Admins are the emails in ADMIN_EMAILS.
Anyone else gets 404 (the page doesn't exist for them). No record text, tokens or keys are ever returned: only
counts, tool names, statuses, short error types and yes/no flags for which services are set up.
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import store, vault
from ..auth import require_login
from ..database import get_db
from ..models import AgentAudit, AgentFile, AgentTask, User
from ..schemas import iso

router = APIRouter(prefix="/api/admin", tags=["admin"])


def admin_user(claims: dict = Depends(require_login), db: Session = Depends(get_db)) -> User:
    allowed = {e.strip().lower() for e in (os.getenv("ADMIN_EMAILS") or "").split(",") if e.strip()}
    user = db.get(User, claims.get("uid") or claims.get("sub"))
    if user is None or user.email.lower() not in allowed:
        raise HTTPException(404, "Not found")
    return user


@router.get("/metrics")
def metrics(days: int = Query(default=7, ge=1, le=30), _: User = Depends(admin_user), db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = list(db.scalars(select(AgentAudit).where(AgentAudit.created_at >= since)))
    tools = [r for r in rows if r.tool != "voice.transcribe" and not r.tool.startswith("files.")]
    by_tool: dict[str, Counter] = {}
    for r in tools:
        by_tool.setdefault(r.tool, Counter())[r.status] += 1
    per_tool = sorted(({"tool": t, "total": sum(c.values()), "ok": c["ok"], "failed": c["failed"] + c["invalid"], "denied": c["denied"],
                        "asked": c["needs_confirmation"], "declined": c["declined"]} for t, c in by_tool.items()), key=lambda x: -x["total"])[:20]
    daily = Counter(r.created_at.date().isoformat() for r in tools)
    voice = Counter((r.detail or "").split(" ")[0] for r in rows if r.tool == "voice.transcribe")
    tasks = list(db.scalars(select(AgentTask).where(AgentTask.created_at >= since)))
    src = Counter((t.result or {}).get("planSource", "rules") for t in tasks)
    recent_fail = sorted((r for r in tools if r.status in ("failed", "denied", "invalid")), key=lambda r: r.created_at, reverse=True)[:15]
    files = db.execute(select(func.count(), func.coalesce(func.sum(AgentFile.size), 0)).where(AgentFile.status != "discarded")).one()
    return {
        "windowDays": days,
        "users": {"patients": db.scalar(select(func.count()).select_from(User).where(User.role == "patient")),
                  "doctors": db.scalar(select(func.count()).select_from(User).where(User.role == "doctor")),
                  "newInWindow": db.scalar(select(func.count()).select_from(User).where(User.created_at >= since))},
        "agent": {"toolCalls": len(tools), "byAgent": dict(Counter(r.agent_type for r in tools)), "byStatus": dict(Counter(r.status for r in tools)),
                  "confirmations": {"asked": sum(r.status == "needs_confirmation" for r in tools), "approved": sum(r.confirmed and r.status == "ok" for r in tools),
                                    "declined": sum(r.status == "declined" for r in tools)},
                  "perTool": per_tool, "daily": [{"date": d, "calls": n} for d, n in sorted(daily.items())]},
        "tasks": {"total": len(tasks), "byStatus": dict(Counter(t.status for t in tasks)), "answeredBy": dict(src)},
        "tokensToday": __import__("app.tokens", fromlist=["today"]).today(),
        "voice": {"clips": sum(voice.values()), "byEngine": dict(voice)},
        "files": {"stored": files[0], "bytes": int(files[1])},
        "recentProblems": [{"tool": r.tool, "status": r.status, "agent": r.agent_type, "detail": (r.detail or "")[:80], "at": iso(r.created_at)} for r in recent_fail],
        "services": {"redis": store.status().get("kind"), "vault": vault.available(), "groq": bool(os.getenv("GROQ_API_KEY")),
                     "gemini": bool(os.getenv("GEMINI_API_KEY")), "elevenlabs": bool(os.getenv("ELEVENLABS_API_KEY")), "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN"))},
    }


@router.get("/live")
def live(_: User = Depends(admin_user)):
    """Live view of the whole system: requests per second, latency, every API copy, worker, scheduler, the upload
    queue and the circuit breakers. Counts only."""
    from .. import metrics
    return metrics.live()
