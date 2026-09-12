"""In-memory limiter. Not globally reliable on multi-instance Vercel."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

_lock = Lock()
_hits: dict[str, list[float]] = defaultdict(list)


def reset() -> None:
    with _lock:
        _hits.clear()


def allow(key: str, limit: int, window_sec: int) -> bool:
    now = time.time()
    bucket = f"{key}:{window_sec}:{limit}"
    with _lock:
        times = [t for t in _hits[bucket] if now - t < window_sec]
        if len(times) >= limit:
            _hits[bucket] = times
            return False
        times.append(now)
        _hits[bucket] = times
        return True


def check(kind: str, identity: str, *, limit: int, window_sec: int) -> bool:
    return allow(f"{kind}:{identity or 'anon'}", limit, window_sec)
