"""Run: python -m tests.test_auth
Guards the /enable /disable /ban /mute authorization: only group admins pass.
"""
import asyncio

from spam_bot.handlers import admin_notifier as a


class _U:
    def __init__(self, uid): self.id = uid

class _Chat:
    def __init__(self, cid): self.id = cid

class _Member:
    def __init__(self, status): self.status = status

class _Bot:
    def __init__(self, status): self._status = status
    async def get_chat_member(self, chat_id, user_id): return _Member(self._status)

class _Msg:
    def __init__(self, from_id=555, status="member", anon=False, chat_id=-1001):
        self.from_user = _U(from_id)
        self.sender_chat = _Chat(chat_id) if anon else None
        self.chat = _Chat(chat_id)
        self.bot = _Bot(status)


def _run(msg):
    return asyncio.run(a._is_group_admin(msg))


def test_regular_member_is_rejected():
    # The bug: a normal member could /disable. Must be False.
    assert _run(_Msg(from_id=555, status="member")) is False

def test_administrator_is_authorized():
    assert _run(_Msg(from_id=555, status="administrator")) is True

def test_creator_is_authorized():
    assert _run(_Msg(from_id=555, status="creator")) is True

def test_anonymous_admin_is_authorized():
    assert _run(_Msg(anon=True)) is True


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
