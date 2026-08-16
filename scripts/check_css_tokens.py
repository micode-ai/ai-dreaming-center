"""Design-system linter: keeps colour out of templates and hex out of components.

Three assertions, each with a per-file counter so migration progress is a number
rather than a feeling:

  1. components.css contains no hex colour literal (#abc / #aabbcc). Colour must
     come from tokens.css via var(). rgba(0, 0, 0, ...) is permitted for shadows
     -- the rule targets palette colour, not black alpha.
  2. No template uses a light-theme Tailwind colour utility.
  3. No template carries a static inline style= attribute. Dynamic
     style="{{ ... }}" is exempt (bar widths and similar).

Run it for its counters during migration; it becomes a gate once it exits 0.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "dreaming" / "templates"
COMPONENTS = ROOT / "dreaming" / "static" / "components.css"

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")

# A Tailwind utility carrying a palette colour. Requires a colour name, so
# layout/size utilities (text-xs, border, bg-none) never match.
COLOUR_UTILITY = re.compile(
    r"\b(?:bg|text|border|divide|ring|from|to|via)-"
    r"(?:white|black|slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|"
    r"green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)"
    r"(?:-\d{2,3})?(?:/\d{1,3})?\b"
)

INLINE_STYLE = re.compile(r'style\s*=\s*"([^"]*)"')


def _hex_in_components() -> list[str]:
    if not COMPONENTS.exists():
        print("SKIP components.css hex check (file does not exist yet)")
        return []
    bad = []
    for i, line in enumerate(COMPONENTS.read_text(encoding="utf-8").splitlines(), 1):
        for m in HEX.finditer(line):
            bad.append(f"components.css:{i}: {m.group(0)}  ({line.strip()[:60]})")
    return bad


def _scan_templates() -> tuple[dict[str, int], dict[str, int]]:
    utilities: dict[str, int] = {}
    inline: dict[str, int] = {}
    for tpl in sorted(TEMPLATES.rglob("*.html")):
        rel = tpl.relative_to(TEMPLATES).as_posix()
        text = tpl.read_text(encoding="utf-8")
        u = len(COLOUR_UTILITY.findall(text))
        # Dynamic styles carry Jinja interpolation and are exempt.
        s = sum(1 for m in INLINE_STYLE.finditer(text) if "{{" not in m.group(1))
        if u:
            utilities[rel] = u
        if s:
            inline[rel] = s
    return utilities, inline


def _report(title: str, counts: dict[str, int]) -> int:
    total = sum(counts.values())
    if not total:
        print(f"OK {title}: 0")
        return 0
    print(f"{title}: {total} across {len(counts)} file(s)")
    for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5d}  {name}")
    return total


def main() -> int:
    failed = False

    hex_bad = _hex_in_components()
    if hex_bad:
        print(f"Hex literals in components.css: {len(hex_bad)}")
        for line in hex_bad:
            print("  " + line)
        failed = True
    elif COMPONENTS.exists():
        # Only claim OK for a file actually read. Before Task 4 creates it,
        # _hex_in_components has already printed its SKIP notice.
        print("OK components.css: no hex literals")

    utilities, inline = _scan_templates()
    if _report("Light-theme colour utilities in templates", utilities):
        failed = True
    if _report("Static inline style= in templates", inline):
        failed = True

    print("FAIL" if failed else "ALL OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
