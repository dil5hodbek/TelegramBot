"""Run: python -m tests.test_crypto  (or pytest). No DB/network required.

Covers crypto.py: Fernet round-trip, garbage decrypt, and missing-secret behaviour.
"""
import os

from cryptography.fernet import Fernet

# Set a real Fernet key before importing the module under test.
_TEST_SECRET = Fernet.generate_key().decode()
os.environ["KEY_ENCRYPTION_SECRET"] = _TEST_SECRET

from spam_bot.core import crypto


def test_available_with_secret():
    assert crypto.available() is True


def test_encrypt_decrypt_roundtrip():
    sample = "AIzaSyFakeKey123456"
    token = crypto.encrypt(sample)
    assert token is not None
    assert token != sample                    # must be ciphertext, not plaintext
    assert crypto.decrypt(token) == sample


def test_decrypt_garbage_returns_none():
    assert crypto.decrypt("notavalidtoken") is None


def test_decrypt_empty_returns_none():
    assert crypto.decrypt("") is None


def test_encrypt_empty_returns_none():
    assert crypto.encrypt("") is None


def test_no_secret_disables_all(monkeypatch):
    saved = os.environ.pop("KEY_ENCRYPTION_SECRET", None)
    try:
        assert crypto.available() is False
        assert crypto.encrypt("anything") is None
        assert crypto.decrypt("anything") is None
    finally:
        if saved is not None:
            os.environ["KEY_ENCRYPTION_SECRET"] = saved


if __name__ == "__main__":
    # manual run without pytest (monkeypatched test skipped)
    simple = [
        test_available_with_secret,
        test_encrypt_decrypt_roundtrip,
        test_decrypt_garbage_returns_none,
        test_decrypt_empty_returns_none,
        test_encrypt_empty_returns_none,
    ]
    for fn in simple:
        fn()
        print(f"ok  {fn.__name__}")
    # manual version of the no-secret test
    saved = os.environ.pop("KEY_ENCRYPTION_SECRET", None)
    assert crypto.available() is False
    assert crypto.encrypt("x") is None
    if saved:
        os.environ["KEY_ENCRYPTION_SECRET"] = saved
    print("ok  test_no_secret_disables_all (manual)")
    print("all passed")
