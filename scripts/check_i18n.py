"""Fail with non-zero exit if RU and EN locales have different keys."""
import json
import sys
from pathlib import Path


def main() -> int:
    base = Path(__file__).resolve().parent.parent / "dreaming" / "i18n"
    ru = json.loads((base / "messages_ru.json").read_text(encoding="utf-8"))
    en = json.loads((base / "messages_en.json").read_text(encoding="utf-8"))
    ru_keys, en_keys = set(ru), set(en)
    only_ru = ru_keys - en_keys
    only_en = en_keys - ru_keys
    if not (only_ru or only_en):
        print("OK: locales have identical key sets")
        return 0
    if only_ru:
        print(f"In RU but not EN ({len(only_ru)}):")
        for k in sorted(only_ru):
            print(f"  - {k}")
    if only_en:
        print(f"In EN but not RU ({len(only_en)}):")
        for k in sorted(only_en):
            print(f"  - {k}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
