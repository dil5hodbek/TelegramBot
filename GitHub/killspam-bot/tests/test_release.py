"""Run: python -m tests.test_release  (or pytest). No DB/network required.

The release-notes parser must return ONLY the top CHANGELOG section (the newest
release), stopping at the next '## ' header.
"""
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")

from spam_bot.core import release

_SAMPLE = """# Changelog

Some preamble text.

## 2026-06-22 — Newest (0.15.0)

### Added
- A shiny thing.

## 2026-06-21 — Older (0.14.0)

### Fixed
- An old thing.
"""


def test_parse_latest_returns_only_top_section():
    out = release._parse_latest(_SAMPLE)
    assert out.startswith("## 2026-06-22 — Newest (0.15.0)")
    assert "A shiny thing." in out
    assert "Older" not in out and "An old thing." not in out


def test_parse_latest_empty_when_no_section():
    assert release._parse_latest("# Changelog\n\njust preamble\n") is None


def test_to_telegram_html_converts_markdown():
    md = "## Title (0.15.0)\n\n### Added\n- A **bold** thing & a `code` bit.\n- Second <item>"
    h = release.to_telegram_html(md)
    assert "<b>Title (0.15.0)</b>" in h
    assert "<b>Added</b>" in h
    assert "• A <b>bold</b> thing &amp; a <code>code</code> bit." in h
    assert "• Second &lt;item&gt;" in h          # HTML special chars escaped
    assert "##" not in h and "- " not in h        # no raw markdown left


def test_latest_notes_html_is_html():
    h = release.latest_notes_html()
    assert h and "<b>" in h
    # No raw markdown headings/bullets left at line starts (escaped '##' inside
    # backtick code spans is fine — that's real content, not a heading).
    assert not any(ln.startswith(("## ", "### ", "- ", "* ")) for ln in h.splitlines())


def test_latest_notes_reads_real_changelog():
    # The repo's own CHANGELOG should parse to a non-empty top section.
    notes = release.latest_notes()
    version = (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip()
    assert notes and notes.startswith("## ")
    assert version in notes  # top entry names the current version


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all passed")
