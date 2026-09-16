import hashlib
import html
from pathlib import Path
from typing import Iterable, Optional


# Bu ro'yxatda faqat aynan joriy versiyadagi o'zgarishlar turadi. Yangi versiya
# tayyorlanganda eski bandlar saqlanmaydi, CURRENT_CHANGES to'liq almashtiriladi.
# Fingerprint o'zgarsa, xabar har bir adminga alohida va faqat bir marta boradi.
CURRENT_VERSION = "2026.09.15-18"
CURRENT_CHANGES = (
    "Yangi cheklangan admin faqat bitta guruh uchun /status, /recent, /report va /dbstats ma'lumotlarini ko'ra oladi; bosh adminning huquqlari o'zgarmadi.",
)


def deployment_fingerprint(package_dir: Optional[Path] = None) -> str:
    root = package_dir or Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def render_update_notice(
    fingerprint: str,
    version: str = CURRENT_VERSION,
    changes: Iterable[str] = CURRENT_CHANGES,
) -> str:
    lines = [
        "✅ <b>Izoh Posbon yangilandi</b>",
        "",
        f"Versiya: <b>{html.escape(version)}</b>",
        f"Yangilanish kodi: <code>{html.escape(fingerprint[:12])}</code>",
        "",
        "<b>Nimalar o'zgardi</b>",
    ]
    lines.extend("• " + html.escape(str(change)) for change in changes)
    lines.extend(("", "Yangilangan panelni ko'rish uchun /start bosing."))
    return "\n".join(lines)
