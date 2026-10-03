"""LLMService: the only place the agent talks to a language model. Swap the class to change provider.

The model gets tool names + schemas and the person's words. It returns JSON. It never receives credentials, never touches
the DB, and anything it returns is validated by the executor before it runs."""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMService(ABC):
    @abstractmethod
    def complete_json(self, system: str, user: str, max_tokens: int = 700) -> dict | None:
        """Return a parsed JSON object, or None on any failure (rate limit, timeout, bad JSON)."""


class GroqLLM(LLMService):
    def complete_json(self, system: str, user: str, max_tokens: int = 700) -> dict | None:
        from ai.consultation import FALLBACK_MODEL, _chat_json  # reuse the fail-fast Groq client and fallback model
        return _chat_json(system, user, max_tokens=max_tokens, fallback_model=FALLBACK_MODEL)


class NullLLM(LLMService):
    """No model: the planner uses rules only. Used in tests and when GROQ_API_KEY is missing."""
    def complete_json(self, system: str, user: str, max_tokens: int = 700) -> dict | None:
        return None


# ---------------------------------------------------------------- native tool calling (the agent loop)

def _groq_chat(messages: list[dict], tools: list[dict], max_tokens: int) -> dict | None:
    """One chat turn with function calling. Fails fast (no SDK retries); on a rate limit, tries the smaller model once."""
    import os
    from groq import Groq
    from ai.consultation import FALLBACK_MODEL, MODEL
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    client = Groq(api_key=key, timeout=25.0, max_retries=0)
    for model in (MODEL, FALLBACK_MODEL):
        try:
            r = client.chat.completions.create(model=model, messages=messages, tools=tools or None, tool_choice="auto" if tools else None,
                                               max_tokens=max_tokens, temperature=0.2, reasoning_effort="low")
        except Exception as e:
            if type(e).__name__ == "RateLimitError":
                continue
            return None
        from app import tokens
        tokens.record("agent-loop", model, getattr(r, "usage", None))
        m = r.choices[0].message
        calls = [{"id": c.id, "name": c.function.name, "arguments": c.function.arguments or "{}"} for c in (m.tool_calls or [])]
        return {"content": (m.content or "").strip(), "tool_calls": calls, "model": model}
    return None


def _base_available(self) -> bool:
    return False


def _base_chat_tools(self, messages: list[dict], tools: list[dict], max_tokens: int = 600) -> dict | None:
    return None


LLMService.available = _base_available
LLMService.chat_tools = _base_chat_tools
GroqLLM.available = lambda self: bool(__import__("os").getenv("GROQ_API_KEY"))
GroqLLM.chat_tools = lambda self, messages, tools, max_tokens=600: _groq_chat(messages, tools, max_tokens)


# ---------------------------------------------------------------- a second, small model that checks the reply

def _groq_judge(system: str, user: str) -> dict | None:
    """One cheap JSON call on the small model (its own quota). None on any failure: the caller decides what that means."""
    import json
    import os
    from groq import Groq
    from ai.consultation import FALLBACK_MODEL
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    try:
        r = Groq(api_key=key, timeout=15.0, max_retries=0).chat.completions.create(
            model=FALLBACK_MODEL, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=500, temperature=0, reasoning_effort="medium", response_format={"type": "json_object"})
        from app import tokens
        tokens.record("agent-judge", FALLBACK_MODEL, getattr(r, "usage", None))
        out = json.loads(r.choices[0].message.content or "{}")
        return out if isinstance(out, dict) else None
    except Exception:
        return None


LLMService.judge = lambda self, system, user: None
GroqLLM.judge = lambda self, system, user: _groq_judge(system, user)
