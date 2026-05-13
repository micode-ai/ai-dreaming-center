"""Fail with non-zero exit if any template still uses native confirm/alert/prompt.

Walks dreaming/templates/**/*.html programmatically (no shell glob — works on
Windows PowerShell and POSIX alike). The pattern matches a function call only
(`confirm(`, `alert(`, `prompt(`), so HTML attributes like 'data-confirm=' and
words inside translated strings are not false-positives.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path


PATTERN = re.compile(r"\b(confirm|alert|prompt)\s*\(")


def main() -> int:
    base = Path(__file__).resolve().parent.parent / "dreaming" / "templates"
    bad: list[tuple[Path, int, str]] = []
    for html in base.rglob("*.html"):
        for i, line in enumerate(html.read_text(encoding="utf-8").splitlines(), 1):
            if PATTERN.search(line):
                bad.append((html, i, line.strip()))
    if not bad:
        print("OK: no native confirm/alert/prompt in templates")
        return 0
    print(f"Found {len(bad)} native dialog call(s):")
    for path, lineno, snippet in bad:
        rel = path.relative_to(base.parent.parent)
        print(f"  {rel}:{lineno}: {snippet}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
