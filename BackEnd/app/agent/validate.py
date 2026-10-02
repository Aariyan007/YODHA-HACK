"""Small JSON-schema checker for tool arguments (type, required, enum, min/max, length, no extra keys).
Tool arguments come from an LLM, so they are treated as untrusted input."""
from __future__ import annotations

from typing import Any

_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}


def check(schema: dict, value: Any, path: str = "args") -> str | None:
    t = schema.get("type")
    if t:
        py = _TYPES[t]
        if not isinstance(value, py) or (t in ("integer", "number") and isinstance(value, bool)):
            return f"{path} must be {t}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path} must be one of {schema['enum']}"
    if t == "string":
        if len(value) > schema.get("maxLength", 2000):
            return f"{path} is too long"
        if len(value) < schema.get("minLength", 0):
            return f"{path} is too short"
    if t in ("integer", "number"):
        if "minimum" in schema and value < schema["minimum"]:
            return f"{path} must be at least {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            return f"{path} must be at most {schema['maximum']}"
    if t == "array":
        if len(value) > schema.get("maxItems", 50):
            return f"{path} has too many items"
        for i, v in enumerate(value):
            if "items" in schema and (e := check(schema["items"], v, f"{path}[{i}]")):
                return e
    if t == "object":
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                return f"{path}.{k} is required"
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(props)
            if extra:
                return f"{path} has unknown field {sorted(extra)[0]}"
        for k, v in value.items():
            if k in props and (e := check(props[k], v, f"{path}.{k}")):
                return e
    return None
