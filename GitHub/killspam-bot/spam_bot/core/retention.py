"""Data retention: drop old spam-report text and spent token grants."""
import logging
from datetime import datetime, timedelta

RETENTION_DAYS = 90


def purge_old() -> None:
    from ..db.session import SessionLocal
    from ..db.models import SpamReport, TokenGrant, TokenUsage
    cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    try:
        with SessionLocal() as db:
            n = db.query(SpamReport).filter(SpamReport.reported_at < cutoff).delete()
            # housekeeping: drop used or expired token grants
            t = db.query(TokenGrant).filter(
                (TokenGrant.used == True) | (TokenGrant.expires_at < datetime.utcnow())  # noqa: E712
            ).delete()
            u = db.query(TokenUsage).filter(TokenUsage.created_at < cutoff).delete()
            db.commit()
        logging.info(f"retention: purged {n} old spam reports, {t} spent tokens, {u} usage rows")
    except Exception as e:
        logging.error(f"retention purge failed: {e}")
