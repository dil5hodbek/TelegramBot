"""Tiny fixed-window rate limiter, used to budget the paid Gemini calls.

Why gate Gemini rather than drop messages: the regex/keyword layer is free and
must always run so spam is still caught; only the external API is the runaway-cost
path the CSO audit flagged ("unbounded Gemini API calls").
ponytail: in-memory, single process; the per-key dict is unbounded by distinct
keys — fine for one bot, swap for cachetools.TTLCache if memory ever matters.
"""
import time


class RateLimiter:
    def __init__(self, limit: int, window: float):
        self.limit = limit
        self.window = window
        self._hits: dict = {}  # key -> (window_start, count)

    def allow(self, key) -> bool:
        now = time.monotonic()
        start, count = self._hits.get(key, (now, 0))
        if now - start > self.window:
            start, count = now, 0
        count += 1
        self._hits[key] = (start, count)
        return count <= self.limit
