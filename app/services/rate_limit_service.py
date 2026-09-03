"""In-process fixed-window rate limiter for the public guest endpoints.

This is intentionally light: a single-process FastAPI deployment is the
default for this project, and abuse mitigation here is layered with WAF
rules + future bot challenges (see BACKEND_PLAN_ON_PLACE_ORDER.md §6).
For multi-worker / multi-host deployments swap the backing dict for a
shared Redis counter.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Callable, Optional

from fastapi import HTTPException, Request, status


_WINDOW_SECONDS = 60


class _FixedWindowCounter:
    """Per-key request counter that resets every `window` seconds."""

    def __init__(self, window: int = _WINDOW_SECONDS) -> None:
        self._window = window
        self._lock = threading.Lock()
        # key -> (window_start_epoch, count)
        self._buckets: dict[str, tuple[float, int]] = defaultdict(
            lambda: (0.0, 0)
        )

    def hit(self, key: str, limit: int) -> tuple[bool, int]:
        """Register a hit on `key`. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            window_start, count = self._buckets[key]
            if now - window_start >= self._window:
                window_start = now
                count = 0
            count += 1
            self._buckets[key] = (window_start, count)
            if count > limit:
                retry_after = max(1, int(self._window - (now - window_start)))
                return False, retry_after
            return True, 0


_counter = _FixedWindowCounter()


def _client_ip(request: Request) -> str:
    """Best-effort client IP. Trust X-Forwarded-For first hop when present —
    the public endpoints sit behind Caddy / a gateway which terminates TLS."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is None:
        return "unknown"
    return request.client.host or "unknown"


def rate_limit(
    name: str,
    *,
    per_ip: int,
    per_ip_restaurant: Optional[int] = None,
    restaurant_param: str = "restaurant_id",
) -> Callable:
    """Build a FastAPI dependency that enforces per-IP (and optionally
    per-(IP, restaurant)) caps within a 60-second window."""

    def dependency(request: Request) -> None:
        ip = _client_ip(request)
        allowed, retry_after = _counter.hit(f"{name}:ip:{ip}", per_ip)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
                headers={
                    "Retry-After": str(retry_after),
                    "RateLimit-Limit": str(per_ip),
                    "RateLimit-Remaining": "0",
                    "RateLimit-Reset": str(retry_after),
                },
            )
        if per_ip_restaurant is not None:
            restaurant_id = request.path_params.get(restaurant_param)
            if restaurant_id is not None:
                key = f"{name}:ip-rest:{ip}:{restaurant_id}"
                allowed, retry_after = _counter.hit(key, per_ip_restaurant)
                if not allowed:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Too many requests for this restaurant",
                        headers={
                            "Retry-After": str(retry_after),
                            "RateLimit-Limit": str(per_ip_restaurant),
                            "RateLimit-Remaining": "0",
                            "RateLimit-Reset": str(retry_after),
                        },
                    )

    return dependency
