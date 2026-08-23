"""Long-form help text for each section, one markdown file per locale.

Kept as files rather than i18n keys: these are pages of prose with headings
and lists, and `messages_*.json` is built for short strings on one line. The
filename is the section key from `nav_sections`, so a section and its help
cannot drift apart without `scripts/smoke_help_sections.py` noticing.

Rendered client-side by `_markdown_partial.html`, the same renderer plans,
ideas and contracts already use.
"""

from __future__ import annotations

from pathlib import Path

HELP_DIR = Path(__file__).resolve().parent.parent / "help"
FALLBACK_LOCALE = "ru"

# (path, mtime) -> text. Content is static in production but edited live in
# development, so the mtime is part of the key rather than a plain lru_cache
# that would serve a stale file until the process restarts.
_cache: dict[tuple[str, float], str] = {}


def _read(path: Path) -> str | None:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    key = (str(path), mtime)
    hit = _cache.get(key)
    if hit is None:
        try:
            hit = path.read_text(encoding="utf-8")
        except OSError:
            return None
        _cache[key] = hit
    return hit


def get(key: str, locale: str) -> str | None:
    """Markdown body for one section, or None if nothing is written yet.

    Falls back to the default locale so a section that exists in Russian but
    not yet in English shows the Russian text rather than an empty panel.
    """
    text = _read(HELP_DIR / locale / f"{key}.md")
    if text is None and locale != FALLBACK_LOCALE:
        text = _read(HELP_DIR / FALLBACK_LOCALE / f"{key}.md")
    return text


def available(locale: str) -> set[str]:
    """Section keys that have a file in this locale. Used by the smoke check."""
    d = HELP_DIR / locale
    if not d.is_dir():
        return set()
    return {p.stem for p in d.glob("*.md")}
