"""Run: python -m pytest tests/test_cleanup.py  (no DB/network).

Covers the auto-cleanup helpers: transient bot notices and admin command
messages are removed from the group, but bot replies in private chats stay.
"""
import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite://")

from spam_bot.handlers import admin_notifier as a


class _Bot:
    def __init__(self):
        self.deleted = []

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


class _Msg:
    def __init__(self, chat_type, bot):
        self.chat = SimpleNamespace(id=10, type=chat_type)
        self.message_id = 99
        self.bot = bot
        self.replies = []

    async def reply(self, text, **kwargs):
        self.replies.append(text)
        return SimpleNamespace(chat=SimpleNamespace(id=10), message_id=500)


def test_delete_after_deletes_the_message():
    bot = _Bot()
    asyncio.run(a._delete_after(bot, 10, 77, 0))
    assert (10, 77) in bot.deleted


def test_reply_temp_schedules_delete_in_group(monkeypatch):
    calls = []
    monkeypatch.setattr(a, "autodelete", lambda bot, c, m, **k: calls.append((c, m)))
    asyncio.run(a.reply_temp(_Msg("supergroup", _Bot()), "hi"))
    assert calls == [(10, 500)]   # the bot's reply (chat 10, msg 500) is scheduled


def test_reply_temp_keeps_replies_in_private(monkeypatch):
    calls = []
    monkeypatch.setattr(a, "autodelete", lambda *args, **k: calls.append(args))
    asyncio.run(a.reply_temp(_Msg("private", _Bot()), "hi"))
    assert calls == []            # DM replies are never auto-deleted


def test_delete_command_removes_incoming_message():
    bot = _Bot()
    asyncio.run(a.delete_command(_Msg("supergroup", bot)))
    assert (10, 99) in bot.deleted


def test_autodelete_no_running_loop_is_noop():
    # Outside an event loop it must not raise (best-effort scheduling).
    a.autodelete(_Bot(), 10, 1)


if __name__ == "__main__":
    import sys
    sys.exit(__import__("pytest").main([__file__, "-q"]))
