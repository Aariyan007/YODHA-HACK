"""Short term chat and session facts live in the store (Redis, memory fallback), keyed per actor and conversation,
with a TTL. Long term context is never copied here, tools read it from the records when needed.
Only the last few turns are kept: what the person typed and the agent's own short replies, never documents.
"""
from __future__ import annotations

import json

from .. import store

TTL = 2 * 60 * 60
MAX_TURNS = 8


def _key(role: str, actor: str, conv: str, kind: str) -> str:
    return f"agent:{kind}:{role}:{actor}:{conv}"


class AgentMemory:
    def history(self, role: str, actor: str, conv: str) -> list[dict]:
        raw = store.get_value(_key(role, actor, conv, "hist"))
        return json.loads(raw) if raw else []

    def add_turn(self, role: str, actor: str, conv: str, user_text: str, agent_text: str) -> None:
        h = self.history(role, actor, conv)
        h.append({"u": user_text[:500], "a": agent_text[:600]})
        store.set_value(_key(role, actor, conv, "hist"), json.dumps(h[-MAX_TURNS:], ensure_ascii=False), ttl=TTL)

    def session(self, role: str, actor: str, conv: str) -> dict:
        raw = store.get_value(_key(role, actor, conv, "sess"))
        return json.loads(raw) if raw else {}

    def set_session(self, role: str, actor: str, conv: str, **facts) -> dict:
        s = {**self.session(role, actor, conv), **facts}
        store.set_value(_key(role, actor, conv, "sess"), json.dumps(s, ensure_ascii=False, default=str), ttl=TTL)
        return s

    def clear(self, role: str, actor: str, conv: str) -> None:
        store.delete(_key(role, actor, conv, "hist"))
        store.delete(_key(role, actor, conv, "sess"))
