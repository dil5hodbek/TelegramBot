"""Run: python -m tests.test_tokens  (or pytest). Temp-file SQLite, no network.

Covers tokens.py: mint→validate→consume→validate-None, and expired token.
"""
import os
import tempfile
from datetime import datetime, timedelta

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_db_path}")

from spam_bot.db.session import engine, Base
from spam_bot.db.models import TokenGrant  # register table with Base  # noqa: F401
Base.metadata.create_all(bind=engine)

from spam_bot.core import tokens
from spam_bot.db.session import SessionLocal


def test_mint_returns_string():
    tok = tokens.mint(chat_id=1001, created_by=999)
    assert isinstance(tok, str) and len(tok) > 10


def test_validate_valid_token():
    tok = tokens.mint(chat_id=1002, created_by=999)
    grant = tokens.validate(tok)
    assert grant is not None
    assert grant["chat_id"] == 1002
    assert grant["created_by"] == 999
    assert grant["token"] == tok


def test_validate_bad_token_returns_none():
    assert tokens.validate("notarealtoken") is None


def test_validate_empty_returns_none():
    assert tokens.validate("") is None


def test_consume_makes_token_invalid():
    tok = tokens.mint(chat_id=1003, created_by=999)
    assert tokens.validate(tok) is not None
    tokens.consume(tok)
    assert tokens.validate(tok) is None


def test_expired_token_returns_none():
    with SessionLocal() as db:
        db.add(TokenGrant(
            token="expiredtoken123",
            chat_id=1004,
            created_by=999,
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        ))
        db.commit()
    assert tokens.validate("expiredtoken123") is None


def test_double_consume_is_safe():
    """Consuming an already-used token should not raise."""
    tok = tokens.mint(chat_id=1005, created_by=999)
    tokens.consume(tok)
    tokens.consume(tok)   # should not raise


if __name__ == "__main__":
    import atexit
    atexit.register(lambda: os.unlink(_db_path))
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
