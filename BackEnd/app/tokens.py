"""Count AI tokens by feature and day, so optimisation is measured, not guessed. Numbers only: no text is ever stored."""
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
        key = f"tok:{date.today().isoformat()}:{feature}:{model}"
        cur = json.loads(store.get_value(key) or "{}")
        cur = {"calls": cur.get("calls", 0) + 1, "prompt": cur.get("prompt", 0) + p, "completion": cur.get("completion", 0) + c,
               "cached": cur.get("cached", 0) + cached}
        store.set_value(key, json.dumps(cur), ttl=8 * 86400)
    except Exception:
        pass


def today() -> list[dict]:
    """Today's totals per feature and model (for the admin page)."""
    out = []
    try:
        pre = f"tok:{date.today().isoformat()}:"
        for k in store.keys_with_prefix(pre) if hasattr(store, "keys_with_prefix") else []:
            _, _, feature, model = k.split(":", 3)
            out.append({"feature": feature, **json.loads(store.get_value(k) or "{}"), "model": model})
    except Exception:
        pass
    return sorted(out, key=lambda r: -r.get("prompt", 0))
