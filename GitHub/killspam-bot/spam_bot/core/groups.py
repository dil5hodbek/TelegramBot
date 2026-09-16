"""Allow-list of groups the bot may moderate. Cost guard: unauthorized groups
get zero classification and zero Gemini calls. Also the future home of per-group
BYOK keys."""
import logging

_allowed: set = set()


def reload() -> None:
    global _allowed
    try:
        from ..db.session import SessionLocal
        from ..db.models import AllowedGroup
        with SessionLocal() as db:
            _allowed = {g.chat_id for g in db.query(AllowedGroup).all()}
    except Exception as e:
        logging.error(f"Failed to load allowed groups: {e}")


def is_allowed(chat_id: int) -> bool:
    return chat_id in _allowed


def allowed_ids() -> set:
    return set(_allowed)


def enable(chat_id: int, by: int) -> None:
    from ..db.session import SessionLocal
    from ..db.models import AllowedGroup
    with SessionLocal() as db:
        row = db.query(AllowedGroup).filter(AllowedGroup.chat_id == chat_id).first()
        if row:
            row.enabled_by = by   # refresh enabler on re-enable (drives the key fallback)
        else:
            db.add(AllowedGroup(chat_id=chat_id, enabled_by=by))
        db.commit()
    reload()


def disable(chat_id: int) -> None:
    from ..db.session import SessionLocal
    from ..db.models import AllowedGroup
    with SessionLocal() as db:
        db.query(AllowedGroup).filter(AllowedGroup.chat_id == chat_id).delete()
        db.commit()
    reload()


def count_by(owner_id: int) -> int:
    """How many groups this admin has /enabled (abuse cap on new setups)."""
    from ..db.session import SessionLocal
    from ..db.models import AllowedGroup
    try:
        with SessionLocal() as db:
            return db.query(AllowedGroup).filter(AllowedGroup.enabled_by == owner_id).count()
    except Exception:
        return 0


def enabled_by(chat_id: int):
    """Telegram id of the admin who ran /enable for this group, or None."""
    from ..db.session import SessionLocal
    from ..db.models import AllowedGroup
    try:
        with SessionLocal() as db:
            row = db.query(AllowedGroup).filter(AllowedGroup.chat_id == chat_id).first()
            return row.enabled_by if row else None
    except Exception:
        return None
