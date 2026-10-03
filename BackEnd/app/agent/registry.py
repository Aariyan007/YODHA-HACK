"""The only way the agent can act. Tool names that aren't registered never run."""
from __future__ import annotations

from .types import ToolSpec


class AgentToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"tool {spec.name} already registered")
        if spec.level >= 3 and not spec.confirmation_required and spec.level != 4:
            raise ValueError(f"{spec.name}: level 3 tools must require confirmation")
        self._tools[spec.name] = spec
        return spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def for_role(self, role: str) -> list[ToolSpec]:
        return [t for t in self._tools.values() if role in t.roles]

    def describe(self, role: str) -> list[dict]:
        """What the planner (LLM) sees: names, descriptions, schemas. Never handlers or permissions."""
        return [{"name": t.name, "description": t.description, "input_schema": t.input_schema, "level": t.level}
                for t in self.for_role(role)]

    def names(self) -> list[str]:
        return sorted(self._tools)


REGISTRY = AgentToolRegistry()


def tool(name: str, description: str, input_schema: dict | None = None, *, permission: str, level: int = 1,
         confirmation_required: bool = False, audit_category: str = "read", roles: tuple[str, ...] = ("patient",),
         verify=None, slow: bool = False, preview=None):
    """Decorator that registers a handler(ctx, args) -> {"data", "blocks", "evidence"}."""
    def wrap(fn):
        REGISTRY.register(ToolSpec(
            name=name, description=description,
            input_schema=input_schema or {"type": "object", "properties": {}, "additionalProperties": False},
            permission=permission, handler=fn, level=level, confirmation_required=confirmation_required,
            audit_category=audit_category, roles=roles, verify=verify, slow=slow, preview=preview))
        return fn
    return wrap
