"""Run: python -m tests.test_routing  (or pytest). No DB/network required.

Covers the per-group alert-routing helpers introduced in Phase 1:
  - _can_moderate: operator id, group admin, and random user cases
  - _group_admin_ids: caching, bot exclusion, fallback on error
  - notify_group: messages sent to enabled_by + live admins; fallback
    to send_to_admins when the recipient set is empty / unreachable
"""
import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite://")  # for direct `python -m` runs

from spam_bot.handlers import admin_notifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


def _make_admin(user_id: int, is_bot: bool = False):
    return SimpleNamespace(user=SimpleNamespace(id=user_id, is_bot=is_bot))


class FakeBot:
    """Minimal async bot stub used by the routing tests."""

    def __init__(self, admin_members=None, fail_get_admins=False):
        self._admin_members = admin_members or []
        self._fail_get_admins = fail_get_admins
        self.sent: list[dict] = []   # records every send_message call

    async def get_chat_administrators(self, chat_id):
        if self._fail_get_admins:
            raise RuntimeError("API error")
        return self._admin_members

    async def send_message(self, chat_id, text, reply_markup=None, **kwargs):
        self.sent.append({"chat_id": chat_id, "text": text})


# ---------------------------------------------------------------------------
# _can_moderate
# ---------------------------------------------------------------------------

def test_can_moderate_operator():
    """A user whose id is in ADMIN_TELEGRAM_IDS is always allowed."""
    admin_notifier.ADMIN_TELEGRAM_IDS = ["999"]
    bot = FakeBot(admin_members=[_make_admin(42)])
    # Patch the cache so we don't need a real API call for this user
    admin_notifier._group_admin_cache.clear()
    result = _run(admin_notifier._can_moderate(bot, chat_id=1001, user_id=999))
    assert result is True


def test_can_moderate_group_admin():
    """A user in the group's live admin list may moderate that group."""
    admin_notifier.ADMIN_TELEGRAM_IDS = ["999"]
    admin_notifier._group_admin_cache.clear()
    bot = FakeBot(admin_members=[_make_admin(200), _make_admin(201)])
    result = _run(admin_notifier._can_moderate(bot, chat_id=2001, user_id=200))
    assert result is True


def test_can_moderate_random_user():
    """A user who is neither operator nor group admin is denied."""
    admin_notifier.ADMIN_TELEGRAM_IDS = ["999"]
    admin_notifier._group_admin_cache.clear()
    bot = FakeBot(admin_members=[_make_admin(200)])
    result = _run(admin_notifier._can_moderate(bot, chat_id=2002, user_id=404))
    assert result is False


# ---------------------------------------------------------------------------
# _group_admin_ids
# ---------------------------------------------------------------------------

def test_group_admin_ids_excludes_bots():
    """Bot members must not appear in the returned id set."""
    admin_notifier._group_admin_cache.clear()
    members = [_make_admin(10), _make_admin(11, is_bot=True), _make_admin(12)]
    bot = FakeBot(admin_members=members)
    ids = _run(admin_notifier._group_admin_ids(bot, chat_id=3001))
    assert ids == {10, 12}
    assert 11 not in ids


def test_group_admin_ids_cached():
    """Second call within TTL hits the cache (bot.get_chat_administrators NOT
    called again — call count stays at 1)."""
    admin_notifier._group_admin_cache.clear()

    call_count = 0

    class CountingBot(FakeBot):
        async def get_chat_administrators(self, chat_id):
            nonlocal call_count
            call_count += 1
            return [_make_admin(50)]

    bot = CountingBot()
    _run(admin_notifier._group_admin_ids(bot, chat_id=4001))
    _run(admin_notifier._group_admin_ids(bot, chat_id=4001))
    assert call_count == 1


def test_group_admin_ids_fallback_on_error():
    """If get_chat_administrators fails and there is no prior cache, return
    an empty set (not an exception)."""
    admin_notifier._group_admin_cache.clear()
    bot = FakeBot(fail_get_admins=True)
    ids = _run(admin_notifier._group_admin_ids(bot, chat_id=5001))
    assert ids == set()


# ---------------------------------------------------------------------------
# notify_group
# ---------------------------------------------------------------------------

def test_notify_group_sends_to_enabled_by_and_admins(monkeypatch):
    """enabled_by id AND each live-admin id all receive the alert."""
    admin_notifier._group_admin_cache.clear()
    monkeypatch.setattr("spam_bot.core.groups.enabled_by", lambda chat_id: 777)
    bot = FakeBot(admin_members=[_make_admin(100), _make_admin(101)])
    _run(admin_notifier.notify_group(bot, chat_id=6001, text="hello"))
    recipients = {m["chat_id"] for m in bot.sent}
    assert 777 in recipients
    assert 100 in recipients
    assert 101 in recipients


def test_notify_group_deduplicates_enabled_by(monkeypatch):
    """If enabled_by is already a live admin, he only gets one DM."""
    admin_notifier._group_admin_cache.clear()
    monkeypatch.setattr("spam_bot.core.groups.enabled_by", lambda chat_id: 100)
    bot = FakeBot(admin_members=[_make_admin(100)])
    _run(admin_notifier.notify_group(bot, chat_id=6002, text="hi"))
    assert len(bot.sent) == 1
    assert bot.sent[0]["chat_id"] == 100


def test_notify_group_no_operator_fallback_when_empty(monkeypatch):
    """When no group admin is reachable, the alert is dropped — it must NOT fall
    back to the operator. Otherwise every keyless stranger group dumps its alerts
    on the operator (the book.uz incident)."""
    admin_notifier._group_admin_cache.clear()
    admin_notifier.ADMIN_TELEGRAM_IDS = ["888"]
    monkeypatch.setattr("spam_bot.core.groups.enabled_by", lambda chat_id: None)

    class NoAdminBot(FakeBot):
        async def get_chat_administrators(self, chat_id):
            return []  # no live admins, nobody started the bot

    bot = NoAdminBot()
    _run(admin_notifier.notify_group(bot, chat_id=7001, text="dropped test"))
    # Operator (888) must never be DMed for a stranger group.
    assert 888 not in [c for c in (m["chat_id"] for m in bot.sent)]
    assert "888" not in [str(m["chat_id"]) for m in bot.sent]
    assert bot.sent == []


if __name__ == "__main__":
    import sys
    # Allow running without pytest (quick sanity check).
    # monkeypatch won't work in this path — skip those tests.
    simple_tests = [
        test_can_moderate_operator,
        test_can_moderate_group_admin,
        test_can_moderate_random_user,
        test_group_admin_ids_excludes_bots,
        test_group_admin_ids_cached,
        test_group_admin_ids_fallback_on_error,
    ]
    for fn in simple_tests:
        fn()
        print(f"ok  {fn.__name__}")
    print("all simple tests passed (monkeypatched tests skipped)")
