"""Run: python -m tests.test_retention  (or pytest). Temp-file SQLite, no network.

Covers retention.purge_old(): old SpamReport rows are dropped, recent ones kept;
used and expired TokenGrant rows are dropped, fresh ones kept.
"""
import os
import tempfile
from datetime import datetime, timedelta

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_db_path}")

from spam_bot.db.session import engine, Base
from spam_bot.db.models import SpamReport, TokenGrant  # register tables  # noqa: F401
Base.metadata.create_all(bind=engine)

from spam_bot.core import retention
from spam_bot.db.session import SessionLocal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count(model) -> int:
    with SessionLocal() as db:
        return db.query(model).count()


def _clear(*models) -> None:
    with SessionLocal() as db:
        for m in models:
            db.query(m).delete()
        db.commit()


# ---------------------------------------------------------------------------
# SpamReport retention
# ---------------------------------------------------------------------------

def test_old_spam_report_is_purged():
    _clear(SpamReport)
    with SessionLocal() as db:
        db.add(SpamReport(
            telegram_id=1, group_id=1,
            message_text="old spam",
            reason="ads",
            reported_at=datetime.utcnow() - timedelta(days=100),
        ))
        db.add(SpamReport(
            telegram_id=2, group_id=1,
            message_text="recent spam",
            reason="ads",
            reported_at=datetime.utcnow() - timedelta(days=10),
        ))
        db.commit()

    assert _count(SpamReport) == 2
    retention.purge_old()
    assert _count(SpamReport) == 1

    with SessionLocal() as db:
        remaining = db.query(SpamReport).one()
    assert remaining.message_text == "recent spam"


# ---------------------------------------------------------------------------
# TokenGrant retention
# ---------------------------------------------------------------------------

def test_used_and_expired_tokens_purged_fresh_kept():
    _clear(TokenGrant)
    now = datetime.utcnow()
    with SessionLocal() as db:
        # used token
        db.add(TokenGrant(token="tok_used", chat_id=1, created_by=1,
                          expires_at=now + timedelta(minutes=10), used=True))
        # expired (not used)
        db.add(TokenGrant(token="tok_expired", chat_id=1, created_by=1,
                          expires_at=now - timedelta(minutes=5), used=False))
        # fresh and valid
        db.add(TokenGrant(token="tok_fresh", chat_id=1, created_by=1,
                          expires_at=now + timedelta(minutes=15), used=False))
        db.commit()

    assert _count(TokenGrant) == 3
    retention.purge_old()
    assert _count(TokenGrant) == 1

    with SessionLocal() as db:
        remaining = db.query(TokenGrant).one()
    assert remaining.token == "tok_fresh"


if __name__ == "__main__":
    import atexit
    atexit.register(lambda: os.unlink(_db_path))
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
