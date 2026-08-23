"""The help page and the sidebar must name the same sections.

They drifted once already: the help page listed 25 project sections while the
sidebar had 26, so the project-level AI radar existed in the nav and nowhere in
the reference. Both now read `dreaming/services/nav_sections.py`; this asserts
the sidebar template really does agree with it, since the sidebar still spells
its links out by hand (each carries an inline SVG).

Run: python scripts/smoke_help_sections.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services.nav_sections import GLOBAL_SECTIONS, PROJECT_SECTIONS  # noqa: E402

SIDEBAR = Path("dreaming/templates/_sidebar.html")

# nav_item('key', base ~ '/path', 'title.key', ...)
NAV_ITEM = re.compile(
    r"nav_item\(\s*'([^']+)'\s*,\s*base\s*~\s*'([^']*)'\s*,\s*'([^']+)'",
)
# The global block is written out longhand: href, then the label key.
GLOBAL_LINK = re.compile(
    r'href="(/[^"]*)"[^>]*>.*?\{\{\s*"([^"]+)"\s*\|\s*t\(', re.S,
)

failures: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"FAIL: {msg}")


def main() -> int:
    text = SIDEBAR.read_text(encoding="utf-8")

    # ---------------------------------------------------------- project nav
    found = [(k, p, t) for k, p, t in NAV_ITEM.findall(text)]
    want = [(s.key, s.path, s.title_key) for s in PROJECT_SECTIONS]
    if found == want:
        print(f"ok: sidebar's {len(found)} project links match the registry, in order")
    else:
        fk = {k for k, _, _ in found}
        wk = {k for k, _, _ in want}
        for k in sorted(wk - fk):
            fail(f"project section '{k}' is in the registry but not in the sidebar")
        for k in sorted(fk - wk):
            fail(f"project section '{k}' is in the sidebar but not in the registry")
        for (k, p, t), (k2, p2, t2) in zip(found, want):
            if k == k2 and (p, t) != (p2, t2):
                fail(f"project section '{k}': sidebar has ({p}, {t}), "
                     f"registry has ({p2}, {t2})")
        if fk == wk and sorted(found) == sorted(want):
            fail("project sections agree but their order does not -- the help "
                 "page follows the registry, so the two pages would disagree")

    # ----------------------------------------------------------- global nav
    tail = text[text.index('sidebar.section.global'):]
    glinks = GLOBAL_LINK.findall(tail)
    # /help is the page itself; it is deliberately not one of its own cards.
    glinks = [(p, t) for p, t in glinks if p != "/help"]
    gwant = [(s.path, s.title_key) for s in GLOBAL_SECTIONS]
    if glinks == gwant:
        print(f"ok: sidebar's {len(glinks)} global links match the registry, in order")
    else:
        fail(f"global links differ:\n  sidebar:  {glinks}\n  registry: {gwant}")

    # ------------------------------------------------------- help text keys
    import json
    msgs = json.loads(Path("dreaming/i18n/messages_ru.json").read_text(encoding="utf-8"))
    missing = [s.key for s in (*GLOBAL_SECTIONS, *PROJECT_SECTIONS)
               if f"help.section.{s.key}" not in msgs]
    if missing:
        fail(f"no help.section.* text for: {', '.join(sorted(set(missing)))}")
    else:
        print("ok: every section in the registry has help text")

    # ------------------------------------------------------------ the paths
    # A registry entry with a plausible-looking but wrong path renders a card
    # that 404s, which is worse than the unclickable card it replaced. Checked
    # against the app's own route table rather than a live server.
    from dreaming.main import app
    routes = {getattr(r, "path", "") for r in app.routes}
    dead = [f"{s.key} -> {s.path}" for s in GLOBAL_SECTIONS
            if s.path not in routes]
    dead += [f"{s.key} -> /p/{{slug}}{s.path}" for s in PROJECT_SECTIONS
             if f"/p/{{slug}}{s.path}" not in routes]
    if dead:
        fail("registry paths with no matching route: " + "; ".join(dead))
    else:
        print(f"ok: all {len(GLOBAL_SECTIONS) + len(PROJECT_SECTIONS)} "
              f"registry paths are registered routes")

    # ----------------------------------------------------------- the guides
    # A guide file whose name matches no section is invisible in the app --
    # nothing renders it and nothing reports it missing. And a guide written
    # in one locale but not the other silently shows Russian to an English
    # reader, so both must land together.
    from dreaming.services import help_content
    keys = {s.key for s in (*GLOBAL_SECTIONS, *PROJECT_SECTIONS)}
    ru, en = help_content.available("ru"), help_content.available("en")
    for loc, have in (("ru", ru), ("en", en)):
        stray = sorted(have - keys)
        if stray:
            fail(f"{loc}: guide file(s) matching no section: {', '.join(stray)}")
    if ru != en:
        fail("guides differ between locales -- "
             f"ru-only: {sorted(ru - en) or '-'}, en-only: {sorted(en - ru) or '-'}")
    # Every section is covered as of the wave that wrote these, so a missing
    # guide is now a regression rather than work not yet done. A new section
    # added to the registry has to arrive with its guide.
    missing = sorted(keys - ru)
    if missing:
        fail(f"section(s) with no guide: {', '.join(missing)}")
    elif ru == en:
        print(f"ok: all {len(keys)} sections have a guide, both locales")

    print("FAIL" if failures else "PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
