"""Shared types for the agent core.

Safety levels (the brief):
  L1  read, no confirmation
  L2  reversible / low risk: navigate, filter, draft, summary, PDF, questions
  L3  data write: confirmation required
  L4  clinically consequential: the agent may only explain, draft, prepare or flag. Never silent, never executed here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

L1, L2, L3, L4 = 1, 2, 3, 4

BLOCK_TYPES = {
    "text", "metric", "document", "timeline_event", "comparison", "evidence", "action", "confirmation",
    "progress", "warning", "error", "pdf", "doctor_match", "care_item", "medication", "navigation",
}


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    permission: str                       # e.g. "records:read"
    handler: Callable[..., dict]          # handler(ctx, args) -> {"data": ..., "blocks": [...], "evidence": [...]}
    level: int = L1
    confirmation_required: bool = False
    audit_category: str = "read"
    roles: tuple[str, ...] = ("patient",)  # which agents may see/call it
    verify: Callable[..., bool] | None = None  # post-action check; failing it turns "ok" into "failed"
    preview: Callable[..., list] | None = None  # preview(ctx, args) -> [{label, value}] shown in the confirmation card
    slow: bool = False                    # may take many seconds (model call): the engine runs it as a background task


@dataclass
class ToolResult:
    ok: bool
    status: str                           # ok | denied | invalid | failed | needs_confirmation | unknown_tool
    tool: str
    data: Any = None
    blocks: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    error: str | None = None
    confirmation: dict | None = None      # set when status == needs_confirmation


def block(type_: str, **fields: Any) -> dict:
    if type_ not in BLOCK_TYPES:
        raise ValueError(f"unknown block type {type_}")
    return {"type": type_, **fields}
