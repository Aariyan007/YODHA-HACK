"""Tiny key-value store. Uses Redis if reachable, else an in-memory dict."""
import os
import time

from . import database  # noqa: F401  (loads .env)

_memory: dict[str, tuple[str, float | None]] = {}
_redis = None
KIND = "memory"

url = os.getenv("REDIS_URL", "").strip()
if url:
    try:
        import redis

        client = redis.Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3, decode_responses=True)
        client.ping()
        _redis = client
        KIND = "redis"
        print("[store] Connected to Redis")
    except Exception as e:
        print(f"[store] Redis unreachable ({type(e).__name__}). Using in-memory store.")
else:
    print("[store] REDIS_URL not set. Using in-memory store.")


def set_value(key: str, value: str, ttl: int | None = None) -> None:
    if _redis is not None:
        _redis.set(key, value, ex=ttl)
        return
    _memory[key] = (value, time.time() + ttl if ttl else None)


def get_value(key: str) -> str | None:
    if _redis is not None:
        return _redis.get(key)
    item = _memory.get(key)
    if item is None:
        return None
    value, expires = item
    if expires is not None and expires < time.time():
        _memory.pop(key, None)
        return None
    return value


def delete(key: str) -> None:
    if _redis is not None:
        _redis.delete(key)
    else:
        _memory.pop(key, None)


def delete_prefix(prefix: str) -> int:
    """Delete every key that starts with `prefix`. Returns how many were removed."""
    if _redis is not None:
        keys = list(_redis.scan_iter(match=f"{prefix}*", count=500))
        return _redis.delete(*keys) if keys else 0
    gone = [k for k in _memory if k.startswith(prefix)]
    for k in gone:
        _memory.pop(k, None)
    return len(gone)
