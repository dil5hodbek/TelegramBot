"""Run: python -m pytest tests/test_usage.py  (in-memory sqlite, no network).

Covers token accounting: cost math, Tashkent day/window boundaries, report
formatting, and SQL aggregation.
"""
import os
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite://")

from spam_bot.db.session import engine, Base, SessionLocal
from spam_bot.db.models import TokenUsage  # register table  # noqa: F401

Base.metadata.create_all(bind=engine)

from spam_bot.core import usage


# --- cost ----------------------------------------------------------------------

def test_cost_usd_default_rates():
    # 1M in + 1M out at $0.30 / $2.50 -> $2.80
    assert abs(usage.cost_usd("gemini-2.5-flash", 1_000_000, 1_000_000) - 2.80) < 1e-9


def test_cost_usd_unknown_model_falls_back_to_default():
    assert abs(usage.cost_usd("mystery", 1_000_000, 0) - 0.30) < 1e-9


def test_cost_usd_respects_overridden_pricing():
    saved = usage.PRICING.copy()
    usage.PRICING["gemini-2.5-flash"] = (1.0, 2.0)
    try:
        assert abs(usage.cost_usd("gemini-2.5-flash", 1_000_000, 1_000_000) - 3.0) < 1e-9
    finally:
        usage.PRICING.clear()
        usage.PRICING.update(saved)


# --- time windows (Tashkent = UTC+5) ------------------------------------------

def test_yesterday_bounds_are_tashkent_calendar_day_in_utc():
    now = datetime(2026, 6, 29, 3, 0, 0)            # 08:00 Tashkent on 6/29
    start, end = usage.yesterday_bounds_utc(now_utc=now)
    assert start == datetime(2026, 6, 27, 19, 0, 0)  # 6/28 00:00 Tashkent
    assert end == datetime(2026, 6, 28, 19, 0, 0)    # 6/29 00:00 Tashkent


def test_seconds_until_hour_same_day():
    now = datetime(2026, 6, 29, 3, 0, 0)            # 08:00 Tashkent
    assert usage.seconds_until_hour(9, now_utc=now) == 3600   # 09:00 is 1h away


def test_seconds_until_hour_rolls_to_tomorrow():
    now = datetime(2026, 6, 29, 5, 0, 0)            # 10:00 Tashkent, past 09:00
    assert usage.seconds_until_hour(9, now_utc=now) == 23 * 3600


# --- formatting ----------------------------------------------------------------

def test_format_window_shows_model_tokens_and_cost():
    rows = [(-100, "gemini-2.5-flash", 1000, 2000, 3000)]
    out = usage.format_window(rows, "Yesterday")
    assert "gemini-2.5-flash" in out
    assert "3,000 tokens" in out
    assert "$0.0053" in out          # 1000/1e6*0.3 + 2000/1e6*2.5
    assert "Total" in out


def test_format_window_empty_says_no_usage():
    assert "(no usage)" in usage.format_window([], "Yesterday")


def test_format_window_per_group_breaks_down_by_group():
    rows = [(-100, "gemini-2.5-flash", 10, 10, 20),
            (-200, "gemini-2.5-flash", 10, 10, 20)]
    out = usage.format_window(rows, "Yesterday", per_group=True)
    assert "Group -100" in out and "Group -200" in out


# --- aggregation ---------------------------------------------------------------

def test_summary_aggregates_by_group_and_model():
    now = datetime.utcnow()
    with SessionLocal() as db:
        db.add_all([
            TokenUsage(group_id=-555, model="gemini-2.5-flash",
                       prompt_tokens=100, completion_tokens=200, total_tokens=300, created_at=now),
            TokenUsage(group_id=-555, model="gemini-2.5-flash",
                       prompt_tokens=50, completion_tokens=50, total_tokens=100, created_at=now),
        ])
        db.commit()
    start, end = usage.rolling_bounds_utc(1)
    rows = usage.summary(start, end, group_id=-555)
    assert len(rows) == 1
    gid, model, prompt, completion, total = rows[0]
    assert (gid, model) == (-555, "gemini-2.5-flash")
    assert (prompt, completion, total) == (150, 250, 400)


def test_summary_excludes_rows_outside_window():
    old = datetime.utcnow() - timedelta(days=40)
    with SessionLocal() as db:
        db.add(TokenUsage(group_id=-777, model="gemini-2.5-flash",
                          prompt_tokens=9, completion_tokens=9, total_tokens=18, created_at=old))
        db.commit()
    start, end = usage.rolling_bounds_utc(7)
    assert usage.summary(start, end, group_id=-777) == []


if __name__ == "__main__":
    import sys
    sys.exit(__import__("pytest").main([__file__, "-q"]))
