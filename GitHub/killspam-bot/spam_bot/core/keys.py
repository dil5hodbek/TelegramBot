"""Per-group BYOK Gemini key storage (encrypted via core.crypto)."""
import logging
from datetime import datetime

from . import crypto


def set_key(group_id: int, plaintext: str, set_by: int) -> bool:
    enc = crypto.encrypt(plaintext)
    if enc is None:
        return False  # no KEY_ENCRYPTION_SECRET configured
    from ..db.session import SessionLocal
    from ..db.models import GroupConfig
    with SessionLocal() as db:
        row = db.get(GroupConfig, group_id)
        if row:
            row.gemini_key_encrypted = enc
            row.key_set_by = set_by
            row.key_set_at = datetime.utcnow()
        else:
            db.add(GroupConfig(chat_id=group_id, gemini_key_encrypted=enc,
                               key_set_by=set_by, key_set_at=datetime.utcnow()))
        db.commit()
    return True


def get_key(group_id):
    if group_id is None:
        return None
    from ..db.session import SessionLocal
    from ..db.models import GroupConfig
    try:
        with SessionLocal() as db:
            row = db.get(GroupConfig, group_id)
        return crypto.decrypt(row.gemini_key_encrypted) if row and row.gemini_key_encrypted else None
    except Exception as e:
        logging.error(f"get_key failed: {e}")
        return None


def has_key(group_id) -> bool:
    return get_key(group_id) is not None
