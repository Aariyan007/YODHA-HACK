"""A small thread-safe cache with a size cap and an expiry, for results kept inside one process.

A plain dict used as a cache never forgets, so in a container that runs for weeks it only grows (and some keys come
from what people type). This one drops the oldest entry past `max_items` and ignores entries older than `ttl`.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any


class LRU:
    def __init__(self, max_items: int = 512, ttl: float = 3600.0):
        self.max_items = max_items
        self.ttl = ttl
        self._d: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            hit = self._d.get(key)
            if hit is None:
                return default
            if time.time() - hit[0] > self.ttl:
                del self._d[key]
                return default
            self._d.move_to_end(key)
            return hit[1]

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._d[key] = (time.time(), value)
            self._d.move_to_end(key)
            while len(self._d) > self.max_items:
                self._d.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._d.clear()

    def __len__(self) -> int:
        return len(self._d)
