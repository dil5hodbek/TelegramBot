"""Run: python -m tests.test_feedback  (or pytest). No DB/network required.

Covers the feedback keyboard layout, the forwarded-sender extraction used by the
"flag account" action, and the in-memory watchlist. (DB persistence is exercised
by a separate smoke run, since in-memory sqlite isn't shared across sessions.)
"""
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite://")

from spam_bot.core import watchlist
from spam_bot.handlers import admin_notifier as a


def test_keyboard_leads_with_relevant_report():
    spam = a._fb_keyboard(True).inline_keyboard
    assert [b.callback_data for b in spam[0]] == ["fb:fp", "fb:fn"]
    clean = a._fb_keyboard(False).inline_keyboard
    assert [b.callback_data for b in clean[0]] == ["fb:fn", "fb:fp"]


def test_keyboard_has_flag_account_teach_and_close():
    cbs = [b.callback_data for row in a._fb_keyboard(True).inline_keyboard for b in row]
    assert {"fb:acct", "fb:teach", "fb:x"} <= set(cbs)


def test_forward_sender_visible_user():
    o = SimpleNamespace(sender_user=SimpleNamespace(id=42, full_name="Bot Guy"))
    assert a._forward_sender(SimpleNamespace(forward_origin=o)) == (42, "Bot Guy")


def test_forward_sender_hidden_by_privacy():
    o = SimpleNamespace(sender_user=None, sender_user_name="Hidden One")
    assert a._forward_sender(SimpleNamespace(forward_origin=o)) == (None, "Hidden One")


def test_forward_sender_not_a_forward():
    assert a._forward_sender(SimpleNamespace(forward_origin=None)) == (None, None)


def test_watchlist_add_and_check():
    assert not watchlist.is_watched(777001)
    watchlist.add(777001)
    assert watchlist.is_watched(777001)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
