"""Smoke check: i18n loader + Russian plural rules."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services.i18n import I18n, russian_plural


def main() -> int:
    i = I18n(Path(__file__).resolve().parent.parent / "dreaming" / "i18n")
    assert i.t("navbar.all_projects", "ru") == "Все проекты"
    assert i.t("navbar.all_projects", "en") == "All Projects"
    assert i.t("missing.key", "en") == "missing.key"

    # CLDR Russian plurals
    assert russian_plural(0) == "many"
    assert russian_plural(1) == "one"
    assert russian_plural(2) == "few"
    assert russian_plural(5) == "many"
    assert russian_plural(11) == "many"
    assert russian_plural(12) == "many"
    assert russian_plural(13) == "many"
    assert russian_plural(14) == "many"
    assert russian_plural(15) == "many"
    assert russian_plural(21) == "one"
    assert russian_plural(22) == "few"
    assert russian_plural(25) == "many"
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
