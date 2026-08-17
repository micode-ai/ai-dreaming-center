"""Design-system linter: keeps colour out of templates and hex out of components.

Three assertions, each with a per-file counter so migration progress is a number
rather than a feeling:

  1. components.css contains no hex colour literal (#abc / #aabbcc) and no
     rgb()/rgba()/hsl()/hsla() colour literal. Colour must come from
     tokens.css via var(). Black via rgb()/rgba() (every colour channel --
     r, g, b, or hsl lightness -- equal to zero, any alpha) is permitted for
     shadows only; a function call with any non-zero colour channel is a
     palette colour smuggled in past var() and is flagged just like hex.
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

# rgb()/rgba()/hsl()/hsla() colour functions. HEX can't see these notations at
# all; a palette colour written this way instead of as hex sailed straight
# through the old check (see dialog.app-modal::backdrop's rgba(15, 23, 42, ...)
# -- Tailwind slate-900, not black, not a shadow).
COLOUR_FUNC = re.compile(r"\b(rgba?|hsla?)\(([^)]*)\)", re.IGNORECASE)
NUM = re.compile(r"-?\d+(?:\.\d+)?%?")


def _is_black_colour_func(func: str, args: str) -> bool | None:
    """True if every colour channel is zero (rgb: r/g/b; hsl: lightness).

    Alpha is ignored -- black at any opacity is a legitimate shadow. Returns
    None if the argument list doesn't parse as at least three numeric
    channels (so it is not treated as a colour function at all).
    """
    nums = NUM.findall(args)
    if len(nums) < 3:
        return None
    try:
        if func.lower().startswith("hsl"):
            return float(nums[2].rstrip("%")) == 0
        return all(float(c.rstrip("%")) == 0 for c in nums[:3])
    except ValueError:
        return None

# A Tailwind utility carrying a palette colour. Requires a colour name, so
# layout/size utilities (text-xs, border, bg-none) never match.
COLOUR_UTILITY = re.compile(
    r"\b(?:bg|text|border|divide|ring|from|to|via)-"
    r"(?:white|black|slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|"
    r"green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)"
    r"(?:-\d{2,3})?(?:/\d{1,3})?\b"
)

INLINE_STYLE = re.compile(r'style\s*=\s*"([^"]*)"')

# ---------------------------------------------------------------- assertion 4
# Every class a template references must be defined in this project's CSS or be
# a Tailwind utility. The wave's own failure mode was nine references to a
# `.strong` that existed nowhere: the colour check passed (no palette utility),
# the compile check passed (valid Jinja), the preservation check passed
# (attributes survived). A class name is just a string to all of them.

CSS_SOURCES = [
    ROOT / "dreaming" / "static" / "app.css",
    ROOT / "dreaming" / "static" / "components.css",
    ROOT / "dreaming" / "static" / "table_tools.css",
    ROOT / "dreaming" / "static" / "orchestration_swimlane.css",
]

CLASS_ATTR = re.compile(r'class\s*=\s*"([^"]*)"')
CLASS_DEF = re.compile(r"\.(-?[A-Za-z_][\w-]*)")

# Tailwind utilities that stand alone, with no value suffix.
TW_EXACT = {
    "flex", "grid", "block", "inline", "inline-block", "inline-flex", "hidden",
    "table", "contents", "relative", "absolute", "fixed", "sticky", "static",
    "truncate", "italic", "underline", "uppercase", "lowercase", "capitalize",
    "container", "border", "rounded", "shadow", "ring", "outline", "transition",
    "transform", "resize", "invisible", "visible", "antialiased", "sr-only",
    "overflow-auto", "overflow-hidden", "overflow-x-auto", "overflow-y-auto",
    # -- added Task 9A, Step 3 triage of the real tree; each confirmed against
    # actual usage before being allowlisted (see task-9A-report.md):
    "normal-case",  # text-transform: none; sibling of uppercase/lowercase/
                     # capitalize above, same Tailwind utility group.
    "dark",  # Tailwind's darkMode:'class' toggle -- literally the class name
             # Tailwind's own docs say to put on an ancestor (here <html>,
             # base.html) when tailwind.config sets darkMode: 'class'
             # (also in base.html). Not a utility with its own CSS rule.
    "group",  # Tailwind's group-state marker: add to a parent, style children
              # with group-hover:/group-focus:. Confirmed paired with
              # group-hover:text-blue-700 in index_dashboard.html.
    "pointer-events-none",  # Tailwind's pointer-events utility. Doesn't
              # decompose under the first-hyphen root split ("pointer" is not
              # a root Tailwind otherwise owns), so listed exact rather than
              # widening TW_ROOTS with an unverified "pointer" prefix.
    "line-clamp-2",  # Tailwind's line-clamp plugin/utility (core since v3.3).
              # Same first-hyphen problem as above ("line" is not a root
              # Tailwind owns -- line-height is "leading-*"), so listed exact
              # for the one value actually observed in the tree.
}

# Roots Tailwind owns; a token is Tailwind-shaped if it starts with one of
# these followed by "-".
TW_ROOTS = (
    "p", "px", "py", "pt", "pb", "pl", "pr", "m", "mx", "my", "mt", "mb", "ml",
    "mr", "w", "h", "min", "max", "text", "bg", "border", "rounded", "shadow",
    "gap", "space", "grid", "col", "row", "items", "justify", "self", "place",
    "flex", "order", "opacity", "z", "top", "bottom", "left", "right", "inset",
    "overflow", "whitespace", "break", "font", "leading", "tracking", "list",
    "divide", "ring", "cursor", "select", "transition", "duration", "ease",
    "translate", "scale", "rotate", "animate", "aspect", "object", "align",
    "from", "to", "via", "fill", "stroke", "backdrop", "filter", "blur",
    # -- added Task 9A, Step 3 triage of the real tree; each confirmed against
    # actual usage before being allowlisted (see task-9A-report.md):
    "shrink",  # Tailwind's flex-shrink utility (shrink-0, shrink). Confirmed
               # on "w-64 shrink-0" in ai_radar.html, a flex sidebar.
    "appearance",  # Tailwind's appearance utility (appearance-none). Confirmed
               # on a custom-styled <select>-like control in _sidebar.html.
)

TW_VARIANTS = (
    "sm:", "md:", "lg:", "xl:", "2xl:", "hover:", "focus:", "focus-visible:",
    "active:", "disabled:", "group-hover:", "dark:", "first:", "last:",
    "odd:", "even:", "print:", "motion-safe:", "motion-reduce:",
)

STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)

SCRIPT_BLOCK = re.compile(r"<script\b[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
STATIC = ROOT / "dreaming" / "static"


def _defined_classes() -> set[str]:
    names: set[str] = set()
    for path in CSS_SOURCES:
        if path.exists():
            names |= set(CLASS_DEF.findall(path.read_text(encoding="utf-8")))
    # Templates may carry their own <style> blocks; those are real definitions.
    for tpl in TEMPLATES.rglob("*.html"):
        for block in STYLE_BLOCK.findall(tpl.read_text(encoding="utf-8")):
            names |= set(CLASS_DEF.findall(block))
    return names


def _js_referenced() -> str:
    """Everything JavaScript in this project, concatenated.

    A class whose only job is to be found by querySelector is correct code, not
    a missing rule. Matching against this blob is deliberately crude: a false
    positive costs nothing, while a false negative would flag working code.
    """
    parts: list[str] = []
    for tpl in TEMPLATES.rglob("*.html"):
        parts.extend(SCRIPT_BLOCK.findall(tpl.read_text(encoding="utf-8")))
    for js in STATIC.glob("*.js"):
        parts.append(js.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _is_tailwind(token: str) -> bool:
    for variant in TW_VARIANTS:
        if token.startswith(variant):
            token = token[len(variant):]
            break
    if token in TW_EXACT:
        return True
    head = token.split("-", 1)[0]
    return head in TW_ROOTS


def _undefined_classes(defined: set[str], js_blob: str) -> dict[str, set[str]]:
    offenders: dict[str, set[str]] = {}
    for tpl in sorted(TEMPLATES.rglob("*.html")):
        rel = tpl.relative_to(TEMPLATES).as_posix()
        for attr in CLASS_ATTR.findall(tpl.read_text(encoding="utf-8")):
            if "{{" in attr or "{%" in attr:
                continue  # class list is built by Jinja; not statically knowable
            for token in attr.split():
                if token in defined or _is_tailwind(token):
                    continue
                if re.search(rf"\b{re.escape(token)}\b", js_blob):
                    continue
                offenders.setdefault(rel, set()).add(token)
    return offenders


def _hex_in_components() -> list[str]:
    if not COMPONENTS.exists():
        print("SKIP components.css hex check (file does not exist yet)")
        return []
    bad = []
    for i, line in enumerate(COMPONENTS.read_text(encoding="utf-8").splitlines(), 1):
        for m in HEX.finditer(line):
            bad.append(f"components.css:{i}: {m.group(0)}  ({line.strip()[:60]})")
        for m in COLOUR_FUNC.finditer(line):
            if _is_black_colour_func(m.group(1), m.group(2)) is False:
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
        print(f"Colour literals in components.css: {len(hex_bad)}")
        for line in hex_bad:
            print("  " + line)
        failed = True
    elif COMPONENTS.exists():
        # Only claim OK for a file actually read. Before Task 4 creates it,
        # _hex_in_components has already printed its SKIP notice.
        print("OK components.css: no hex or non-black colour-function literals")

    utilities, inline = _scan_templates()
    if _report("Light-theme colour utilities in templates", utilities):
        failed = True
    if _report("Static inline style= in templates", inline):
        failed = True

    undefined = _undefined_classes(_defined_classes(), _js_referenced())
    if undefined:
        total = sum(len(v) for v in undefined.values())
        print(f"Classes referenced but never defined: {total}")
        for name, tokens in sorted(undefined.items()):
            print(f"  {name}: {', '.join(sorted(tokens))}")
        failed = True
    else:
        print("OK every referenced class is defined or a Tailwind utility")

    print("FAIL" if failed else "ALL OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
