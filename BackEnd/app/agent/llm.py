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
