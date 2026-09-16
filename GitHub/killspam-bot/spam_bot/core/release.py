"""Release-notes announcing: on a version bump, DM the latest CHANGELOG section
to admins. Last-announced version is persisted in app_state so restarts on the
same version don't re-send.
"""
import html
import logging
import re
from pathlib import Path

_CHANGELOG = Path(__file__).resolve().parents[2] / "CHANGELOG.md"
_STATE_KEY = "last_announced_version"


def _inline_md_to_html(s: str) -> str:
    """Escape HTML, then map the inline markdown we use: **bold**, `code`."""
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def to_telegram_html(section: str) -> str:
    """Markdown changelog section -> Telegram-flavoured HTML. Telegram renders
    neither '##' headings nor '-' bullets, so we convert: headings -> bold,
    list items -> '• ', inline **/` preserved."""
    out = []
    for ln in section.splitlines():
        st = ln.strip()
        if not st:
            out.append("")
        elif st.startswith("### "):
            out.append(f"<b>{_inline_md_to_html(st[4:])}</b>")
        elif st.startswith("## "):
            out.append(f"<b>{_inline_md_to_html(st[3:])}</b>")
        elif st.startswith(("- ", "* ")):
            out.append(f"• {_inline_md_to_html(st[2:])}")
        else:
            out.append(_inline_md_to_html(st))
    return "\n".join(out).strip()


def _parse_latest(text: str) -> str | None:
    """Return the top changelog section: from the first '## ' header up to (but
    not including) the next '## '. None if there's no section."""
    out, started = [], False
    for ln in text.splitlines():
        if ln.startswith("## "):
            if started:
                break
            started = True
        if started:
            out.append(ln)
    s = "\n".join(out).strip()
    return s or None


def latest_notes() -> str | None:
    try:
        return _parse_latest(_CHANGELOG.read_text(encoding="utf-8"))
    except Exception as e:
        logging.warning(f"Couldn't read CHANGELOG for release notes: {e}")
        return None


def latest_notes_html(max_len: int = 3000) -> str | None:
    """Top changelog section as Telegram HTML. Truncates the source (not the
    HTML) so we never cut a tag in half."""
    notes = latest_notes()
    if not notes:
        return None
    if len(notes) > max_len:
        notes = notes[:max_len].rsplit("\n", 1)[0] + "\n…"
    return to_telegram_html(notes)


def get_state(key: str, default=None):
    try:
        from ..db.session import SessionLocal
        from ..db.models import AppState
        with SessionLocal() as db:
            row = db.get(AppState, key)
            return row.value if row else default
    except Exception as e:
        logging.error(f"app_state read failed: {e}")
        return default


def set_state(key: str, value: str) -> None:
    from ..db.session import SessionLocal
    from ..db.models import AppState
    with SessionLocal() as db:
        row = db.get(AppState, key)
        if row:
            row.value = value
        else:
            db.add(AppState(key=key, value=value))
        db.commit()


def already_announced(version: str) -> bool:
    return get_state(_STATE_KEY) == version


def mark_announced(version: str) -> None:
    set_state(_STATE_KEY, version)
