"""Tiny key-value store. Uses Redis if it can be reached, else an in-memory dict."""
import logging
import os
import time

from . import database  # noqa: F401  (loads .env)

_memory: dict[str, tuple[str, float | None]] = {}
_redis = None
KIND = "memory"
_degraded = False  # True after a Redis error at runtime: we use memory until the next successful call

log = logging.getLogger("store")

url = os.getenv("REDIS_URL", "").strip()


def _connect(retries: int = 5, wait: float = 1.0) -> None:
    """Connects to Redis, retrying a few times (in Docker, Redis can be a second behind the backend)."""
    global _redis, KIND
    import redis

    last = None
    for attempt in range(1, retries + 1):
        try:
            client = redis.Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3, decode_responses=True)
            client.ping()
            _redis, KIND = client, "redis"
            print("[store] Connected to Redis")
            return
        except Exception as e:
            last = e
            time.sleep(wait)
    print(f"[store] Redis unreachable after {retries} tries ({type(last).__name__}). Using the in-memory store.")


if url:
    _connect()
else:
    print("[store] REDIS_URL not set. Using in-memory store.")


def _redis_call(fn, fallback):
    """Runs a Redis operation. On any error it logs once and uses the in-memory fallback instead of failing the request."""
    global _degraded
    try:
        out = fn()
        _degraded = False
        return out
    except Exception as e:
        if not _degraded:
            log.warning("redis error (%s); using memory until it recovers", type(e).__name__)
        _degraded = True
        return fallback()


def status() -> dict:
    """For /api/health/ready: which backend is in use and whether Redis answers right now."""
    if _redis is None:
        return {"kind": "memory", "ok": True, "detail": "Redis not configured or unreachable at start"}
    try:
        _redis.ping()
        return {"kind": "redis", "ok": True, "detail": "PONG"}
    except Exception as e:
        return {"kind": "redis", "ok": False, "detail": type(e).__name__}


def _mem_set(key: str, value: str, ttl: int | None) -> None:
    _memory[key] = (value, time.time() + ttl if ttl else None)


def _mem_get(key: str) -> str | None:
    item = _memory.get(key)
    if item is None:
        return None
    value, expires = item
    if expires is not None and expires < time.time():
        _memory.pop(key, None)
        return None
    return value


def set_value(key: str, value: str, ttl: int | None = None) -> None:
    if _redis is not None:
        _redis_call(lambda: _redis.set(key, value, ex=ttl), lambda: _mem_set(key, value, ttl))
        return
    _mem_set(key, value, ttl)


def get_value(key: str) -> str | None:
    if _redis is not None:
        return _redis_call(lambda: _redis.get(key), lambda: _mem_get(key))
    return _mem_get(key)


def delete(key: str) -> None:
    if _redis is not None:
        _redis_call(lambda: _redis.delete(key), lambda: _memory.pop(key, None))
    else:
        _memory.pop(key, None)


def delete_prefix(prefix: str) -> int:
    """Deletes every key that starts with `prefix`. Returns how many were removed."""
    def mem() -> int:
        gone = [k for k in _memory if k.startswith(prefix)]
        for k in gone:
            _memory.pop(k, None)
        return len(gone)

    if _redis is not None:
        def real() -> int:
            keys = list(_redis.scan_iter(match=f"{prefix}*", count=500))
            return _redis.delete(*keys) if keys else 0
        return _redis_call(real, mem)
    return mem()


def keys_with_prefix(prefix: str) -> list[str]:
    def mem() -> list[str]:
        return [k for k in _memory if k.startswith(prefix)]

    if _redis is not None:
        return _redis_call(lambda: [k.decode() if isinstance(k, bytes) else k for k in _redis.scan_iter(match=f"{prefix}*", count=500)], mem)
    return mem()


# ---- leases (leader election): only one process holds a named job at a time ----

_LEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  redis.call('expire', KEYS[1], ARGV[2]) return 1
end
if redis.call('set', KEYS[1], ARGV[1], 'NX', 'EX', ARGV[2]) then return 1 end
return 0
"""


def hold_lease(key: str, owner: str, ttl: int) -> bool:
    """Take or renew a lease. True if `owner` holds it now. Atomic in Redis, so two schedulers can't both win."""
    def mem() -> bool:
        cur = _mem_get(key)
        if cur in (None, owner):
            _mem_set(key, owner, ttl)
            return True
        return False

    if _redis is not None:
        return bool(_redis_call(lambda: _redis.eval(_LEASE_LUA, 1, key, owner, ttl), mem))
    return mem()


def lease_owner(key: str) -> str | None:
    return get_value(key)
