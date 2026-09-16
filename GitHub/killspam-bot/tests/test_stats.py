"""Run: python -m pytest tests/test_stats.py  (in-memory sqlite, no network).

Covers the operator stats report: group inventory, per-window spam/ban counts,
and title labelling.
"""
import os
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite://")

from spam_bot.db.session import engine, Base, SessionLocal
from spam_bot.db.models import SpamReport, BlockedUser, AllowedGroup  # noqa: F401

Base.metadata.create_all(bind=engine)

from spam_bot.core import stats, groups


def _reset():
    with SessionLocal() as db:
        for m in (SpamReport, BlockedUser, AllowedGroup):
            db.query(m).delete()
        db.commit()


def test_counts_window_and_grouping():
    _reset()
    now = datetime.utcnow()
    old = now - timedelta(days=40)
    with SessionLocal() as db:
        db.add_all([
            SpamReport(telegram_id=1, group_id=-100, message_text="x", reason="ads", reported_at=now),
            SpamReport(telegram_id=2, group_id=-100, message_text="y", reason="ads", reported_at=now),
            SpamReport(telegram_id=3, group_id=-200, message_text="z", reason="ads", reported_at=now),
            SpamReport(telegram_id=4, group_id=-100, message_text="old", reason="ads", reported_at=old),
            BlockedUser(telegram_id=1, group_id=-100, reason="ads", blocked_at=now),
        ])
        db.commit()
    start, end = stats.usage.rolling_bounds_utc(7)
    spam = stats.spam_counts(start, end)
    assert spam == {-100: 2, -200: 1}          # 40-day-old row excluded
    assert stats.ban_counts(start, end) == {-100: 1}


def test_inventory_reports_ai_flag():
    _reset()
    with SessionLocal() as db:
        db.add(AllowedGroup(chat_id=-100, enabled_by=7, enabled_at=datetime.utcnow()))
        db.commit()
    inv = stats.group_inventory()
    assert len(inv) == 1
    cid, _at, ai_on = inv[0]
    assert cid == -100 and ai_on is False       # no key stored -> regex only


def test_report_uses_titles_and_shows_totals():
    _reset()
    now = datetime.utcnow()
    with SessionLocal() as db:
        db.add(AllowedGroup(chat_id=-100, enabled_by=7, enabled_at=now))
        db.add(SpamReport(telegram_id=1, group_id=-100, message_text="x", reason="ads", reported_at=now))
        db.commit()
    out = stats.report(titles={-100: "Backend Devs"})
    assert "1 group(s) protected" in out
    assert "Backend Devs (-100)" in out
    assert "spam removed" in out


def test_count_by_owner_for_abuse_cap():
    _reset()
    with SessionLocal() as db:
        db.add_all([
            AllowedGroup(chat_id=-1, enabled_by=42, enabled_at=datetime.utcnow()),
            AllowedGroup(chat_id=-2, enabled_by=42, enabled_at=datetime.utcnow()),
            AllowedGroup(chat_id=-3, enabled_by=99, enabled_at=datetime.utcnow()),
        ])
        db.commit()
    assert groups.count_by(42) == 2
    assert groups.count_by(99) == 1
    assert groups.count_by(7) == 0


if __name__ == "__main__":
    import sys
    sys.exit(__import__("pytest").main([__file__, "-q"]))
