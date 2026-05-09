"""Lightweight i18n: load JSON dicts, provide t() with optional plural support."""
from __future__ import annotations
import json
from pathlib import Path


_DEFAULT_LOCALE = "ru"
_FALLBACK_LOCALE = "ru"


class I18n:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.messages: dict[str, dict[str, str]] = {}
        for locale in ("ru", "en"):
            p = base_dir / f"messages_{locale}.json"
            if p.exists():
                self.messages[locale] = json.loads(p.read_text(encoding="utf-8"))
            else:
                self.messages[locale] = {}

    def t(self, key: str, locale: str | None = None, **fmt) -> str:
        loc = locale or _DEFAULT_LOCALE
        msg = self.messages.get(loc, {}).get(key)
        if msg is None and loc != _FALLBACK_LOCALE:
            msg = self.messages.get(_FALLBACK_LOCALE, {}).get(key)
        if msg is None:
            return key
        if fmt:
            try:
                return msg.format(**fmt)
            except (KeyError, IndexError):
                return msg
        return msg

    def plural(self, key_base: str, n: int, locale: str | None = None) -> str:
        loc = locale or _DEFAULT_LOCALE
        category = russian_plural(n) if loc == "ru" else english_plural(n)
        return self.t(f"{key_base}.{category}", locale=loc, n=n)


def russian_plural(n: int) -> str:
    """CLDR rules for Russian counts."""
    n = abs(int(n))
    mod10, mod100 = n % 10, n % 100
    if mod10 == 1 and mod100 != 11:
        return "one"
    if mod10 in (2, 3, 4) and mod100 not in (12, 13, 14):
        return "few"
    return "many"


def english_plural(n: int) -> str:
    return "one" if abs(int(n)) == 1 else "other"
