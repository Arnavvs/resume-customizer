"""Simple in-memory, per-IP sliding-window rate limit for anything that spends LLM quota.
Shared by the REST API and the MCP server, so both count against the same budget."""

import time
from collections import defaultdict, deque

from starlette.requests import Request

from .config import get_settings

WINDOW_SECONDS = 3600
_hits: dict[str, deque[float]] = defaultdict(deque)


class RateLimitExceeded(Exception):
    message = "You've hit the hourly request limit for this demo. Please try again later."


def client_ip(request: Request | None) -> str:
    if request is None:
        return "unknown"
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def check(ip: str) -> None:
    now = time.monotonic()
    hits = _hits[ip]
    while hits and now - hits[0] > WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= get_settings().rate_limit_per_hour:
        raise RateLimitExceeded(RateLimitExceeded.message)
    hits.append(now)


def reset() -> None:
    _hits.clear()
