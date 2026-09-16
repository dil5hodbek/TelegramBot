"""Run: python -m tests.test_mute  (or pytest). No DB/network required.

Covers /mute argument parsing: hours and optional reason.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")

from spam_bot.handlers import admin_notifier as a


def test_no_args_is_24h_no_reason():
    assert a._parse_mute_args(None) == (24, None)
    assert a._parse_mute_args("") == (24, None)
    assert a._parse_mute_args("   ") == (24, None)


def test_hours_only():
    assert a._parse_mute_args("6") == (6, None)


def test_hours_and_reason():
    assert a._parse_mute_args("6 spamming links") == (6, "spamming links")


def test_reason_only_defaults_to_24h():
    assert a._parse_mute_args("spamming links") == (24, "spamming links")


def test_hours_are_clamped():
    assert a._parse_mute_args("0") == (1, None)        # min 1
    assert a._parse_mute_args("99999") == (8760, None)  # max 1 year


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
