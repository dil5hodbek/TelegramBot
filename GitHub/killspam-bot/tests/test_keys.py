"""Run: python -m tests.test_keys  (or pytest). Uses a temp-file SQLite DB.

Covers keys.py: set_key/get_key/has_key round-trip and get_key(None) sentinel.
"""
import os
import tempfile

# Temp file SQLite — set before any spam_bot import so session.py picks it up.
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_db_path}")

from cryptography.fernet import Fernet
os.environ["KEY_ENCRYPTION_SECRET"] = Fernet.generate_key().decode()

# Import session + models so Base.metadata knows about GroupConfig, then create tables.
from spam_bot.db.session import engine, Base
from spam_bot.db.models import GroupConfig  # registers the table with Base  # noqa: F401
Base.metadata.create_all(bind=engine)

from spam_bot.core import keys


def test_set_key_returns_true():
    assert keys.set_key(1001, "AIzaSyFakeKey", set_by=999) is True


def test_get_key_roundtrip():
    keys.set_key(1002, "AIzaSyRoundTrip", set_by=999)
    assert keys.get_key(1002) == "AIzaSyRoundTrip"


def test_has_key_true_after_set():
    keys.set_key(1003, "AIzaSySomeKey", set_by=999)
    assert keys.has_key(1003) is True


def test_has_key_false_for_unknown_group():
    assert keys.has_key(99999) is False


def test_get_key_none_for_none_group():
    assert keys.get_key(None) is None


def test_overwrite_key():
    keys.set_key(1004, "AIzaSyFirst", set_by=1)
    keys.set_key(1004, "AIzaSySecond", set_by=1)
    assert keys.get_key(1004) == "AIzaSySecond"


def test_set_key_false_without_secret(monkeypatch):
    saved = os.environ.pop("KEY_ENCRYPTION_SECRET", None)
    try:
        assert keys.set_key(1005, "AIzaSyAny", set_by=1) is False
    finally:
        if saved is not None:
            os.environ["KEY_ENCRYPTION_SECRET"] = saved


if __name__ == "__main__":
    import atexit

    atexit.register(lambda: os.unlink(_db_path))
    simple = [
        test_set_key_returns_true,
        test_get_key_roundtrip,
        test_has_key_true_after_set,
        test_has_key_false_for_unknown_group,
        test_get_key_none_for_none_group,
        test_overwrite_key,
    ]
    for fn in simple:
        fn()
        print(f"ok  {fn.__name__}")
    # manual version of the no-secret test
    saved = os.environ.pop("KEY_ENCRYPTION_SECRET", None)
    assert keys.set_key(9999, "x", set_by=1) is False
    if saved:
        os.environ["KEY_ENCRYPTION_SECRET"] = saved
    print("ok  test_set_key_false_without_secret (manual)")
    print("all passed")
