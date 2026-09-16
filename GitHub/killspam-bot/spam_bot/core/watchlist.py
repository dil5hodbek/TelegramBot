"""Admin-flagged suspicious accounts: bot profiles whose MESSAGE looked fine but
whose profile links to spam/explicit content (e.g. an attractive non-explicit
photo + a bio link to a private channel). We never auto-ban these — when a
watched account posts in a protected group we just alert admins to decide.

Backed by FeedbackReport rows with label='suspicious_account'. In-memory set,
reloaded at startup and whenever an admin flags a new account.
"""
import logging

_watched: set = set()


def reload() -> None:
    global _watched
    try:
        from ..db.session import SessionLocal
        from ..db.models import FeedbackReport
        with SessionLocal() as db:
            rows = (
                db.query(FeedbackReport.group_id, FeedbackReport.target_user_id)
                .filter(FeedbackReport.label == "suspicious_account",
                        FeedbackReport.target_user_id.isnot(None))
                .all()
            )
            _watched = {(gid, uid) for gid, uid in rows}
    except Exception as e:
        logging.error(f"Failed to load watchlist: {e}")


def is_watched(user_id: int, group_id=None) -> bool:
    """True if user is on the global watchlist OR on this group's watchlist."""
    return (None, user_id) in _watched or (group_id, user_id) in _watched


def add(user_id: int, group_id=None) -> None:
    _watched.add((group_id, user_id))
