"""Counts AI tokens by feature and day, so we measure instead of guessing. Numbers only, no text is ever stored."""
from __future__ import annotations

import json
from datetime import date

from . import store


def record(feature: str, model: str, usage) -> None:
    """usage is the SDK's usage object (prompt_tokens, completion_tokens, optional cached tokens). Never raises."""
    try:
        if usage is None:
            return
        p = int(getattr(usage, "prompt_tokens", 0) or 0)
        c = int(getattr(usage, "completion_tokens", 0) or 0)
        det = getattr(usage, "prompt_tokens_details", None)
        cached = int(getattr(det, "cached_tokens", 0) or 0) if det is not None else 0
        base = f"tok:{date.today().isoformat()}:{feature}:{model}"
        for field, n in (("calls", 1), ("prompt", p), ("completion", c), ("cached", cached)):
            if n:
                store.incr(f"{base}:{field}", ttl=8 * 86400, by=n)   # one atomic add each: no lost updates across copies
    except Exception:
        pass


def today() -> list[dict]:
    """Today's totals per feature and model (for the admin page)."""
    rows: dict[tuple[str, str], dict] = {}
    try:
        pre = f"tok:{date.today().isoformat()}:"
        for k in store.keys_with_prefix(pre):
            parts = k[len(pre):].split(":")
            if len(parts) != 3:
                continue   # a key from the older one-JSON-per-model layout
            feature, model, field = parts
            row = rows.setdefault((feature, model), {"feature": feature, "model": model, "calls": 0, "prompt": 0, "completion": 0, "cached": 0})
            row[field] = int(store.get_value(k) or 0)
    except Exception:
        pass
    return sorted(rows.values(), key=lambda r: -r.get("prompt", 0))
