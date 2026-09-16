"""Run: python -m tests.test_burst  (or pytest). No DB/network required.

Covers the coordinated-spam burst detector: same message from N distinct
accounts -> coordinated spam; one account repeating itself, or short chatter,
must NOT trip it.
"""
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite://")  # for direct `python -m` runs (no conftest)

from spam_bot.handlers import spam_detector as sd

LONG = "free solana case drop open yours now claim airdrop"  # >= _BURST_MIN_LEN


def _msg(chat_id, user_id, message_id):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        from_user=SimpleNamespace(id=user_id),
        message_id=message_id,
    )


def test_burst_triggers_on_distinct_users():
    sd._clear_burst_chat(1)
    assert sd._record_burst(_msg(1, 100, 1), LONG) == (False, None)
    assert sd._record_burst(_msg(1, 101, 2), LONG) == (False, None)
    is_spam, cohort = sd._record_burst(_msg(1, 102, 3), LONG)
    assert is_spam and cohort is not None
    assert {uid for uid, _ in cohort} == {100, 101, 102}
    # Already flagged: still spam, but no second cohort purge.
    assert sd._record_burst(_msg(1, 103, 4), LONG) == (True, None)


def test_one_user_repeating_is_not_a_burst():
    sd._clear_burst_chat(2)
    last = (None, None)
    for mid in range(5):
        last = sd._record_burst(_msg(2, 500, mid), LONG)
    assert last == (False, None)  # one sender flooding != coordinated


def test_short_messages_ignored():
    sd._clear_burst_chat(3)
    for uid in (1, 2, 3, 4):
        assert sd._record_burst(_msg(3, uid, uid), "rahmat") == (False, None)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
