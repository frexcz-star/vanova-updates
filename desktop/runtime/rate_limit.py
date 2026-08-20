"""Simple in-memory rate limiting for runtime endpoints (Phase 6)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict

_lock = threading.Lock()
_buckets: dict[str, list[float]] = defaultdict(list)

# (max_requests, window_seconds)
LIMITS: dict[str, tuple[int, int]] = {
    "hermes": (20, 60),
    "tasks": (30, 60),
}


def check_rate_limit(category: str, client_key: str) -> tuple[bool, str]:
    """Return (allowed, error_message)."""
    limit = LIMITS.get(category)
    if not limit:
        return True, ""
    max_requests, window = limit
    now = time.time()
    bucket_key = f"{category}:{client_key}"
    with _lock:
        window_start = now - window
        attempts = [t for t in _buckets[bucket_key] if t >= window_start]
        if len(attempts) >= max_requests:
            return False, f"Límite de solicitudes alcanzado ({max_requests}/{window}s)"
        attempts.append(now)
        _buckets[bucket_key] = attempts
    return True, ""


def reset_for_tests() -> None:
    with _lock:
        _buckets.clear()
