"""Request limiter.

``allow`` is an in-memory sliding window: exact, but each Vercel instance has
its own counters. ``check(..., shared=True)`` counts in Postgres through the
``lasermcp_rate_hit`` function (migrations/0005_rate_limits.sql) so every
instance sees the same total. Until that migration is applied, or whenever the
call fails, the shared check falls back to the in-memory window instead of
blocking or waving everyone through.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections import defaultdict
from threading import Lock

_lock = Lock()
_hits: dict[str, list[float]] = defaultdict(list)

# After a failed shared call, stay on the in-memory window for a while rather than
# adding a failing round-trip to every request.
_SHARED_TIMEOUT_SEC = 2.5
_RETRY_AFTER_ERROR_SEC = 60
_RETRY_AFTER_MISSING_SEC = 600
_shared_off_until = 0.0


def reset() -> None:
    global _shared_off_until
    with _lock:
        _hits.clear()
        _shared_off_until = 0.0


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


def _shared_hit(key: str, limit: int, window_sec: int) -> bool | None:
    """True/False from the shared counter; None when it cannot be consulted."""
    global _shared_off_until
    from persist.env import supabase_service_role, supabase_url, uses_supabase_app_db

    if not uses_supabase_app_db() or time.time() < _shared_off_until:
        return None
    # Identities are IPs and emails; the table only ever sees a digest.
    bucket = hashlib.sha256(f"{key}:{window_sec}:{limit}".encode("utf-8")).hexdigest()[:40]
    role = supabase_service_role()
    request = urllib.request.Request(
        f"{supabase_url()}/rest/v1/rpc/lasermcp_rate_hit",
        data=json.dumps({"p_bucket": bucket, "p_limit": int(limit), "p_window_sec": int(window_sec)}).encode("utf-8"),
        method="POST",
        headers={"apikey": role, "Authorization": f"Bearer {role}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_SHARED_TIMEOUT_SEC) as response:
            verdict = json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        _shared_off_until = time.time() + (_RETRY_AFTER_MISSING_SEC if exc.code == 404 else _RETRY_AFTER_ERROR_SEC)
        return None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        _shared_off_until = time.time() + _RETRY_AFTER_ERROR_SEC
        return None
    return verdict if isinstance(verdict, bool) else None


def check(kind: str, identity: str, *, limit: int, window_sec: int, shared: bool = False) -> bool:
    key = f"{kind}:{identity or 'anon'}"
    if shared:
        verdict = _shared_hit(key, limit, window_sec)
        if verdict is not None:
            return verdict
    return allow(key, limit, window_sec)
