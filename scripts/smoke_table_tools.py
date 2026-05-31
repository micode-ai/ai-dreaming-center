"""Smoke guard for the shared table-tools component.

Cheap, no-network static checks:
  1. Both static assets exist and are non-empty.
  2. table_tools.js exposes the auto-init API and the custom-predicate registry.
  3. base.html loads both assets.
  4. Every shipped <table> in templates/ is either opted into data-table-tools
     or explicitly allow-listed (so a new bare table is caught in review).
"""
from __future__ import annotations
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "dreaming" / "static"
TEMPLATES = ROOT / "dreaming" / "templates"

# Tables intentionally without sort/filter (justify each entry).
ALLOWLIST: set[str] = {
    # Dead/unused template (run detail UI lives in project_orchestration_list.html).
    "project_orchestration_detail.html",
}

def _check_assets() -> None:
    js = (STATIC / "table_tools.js").read_text(encoding="utf-8")
    css = (STATIC / "table_tools.css").read_text(encoding="utf-8")
    assert "querySelectorAll(\"table[data-table-tools]\")" in js, "auto-init selector missing"
    assert "tableToolsFilters" in js, "custom-predicate registry missing"
    assert "table-tools:changed" in js, "change event missing"
    assert "[data-table-tools]" in css, "css not scoped to component"
    print("OK assets present + API intact")

def _check_base_wires() -> None:
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "/static/table_tools.js" in base, "base.html does not load table_tools.js"
    assert "/static/table_tools.css" in base, "base.html does not load table_tools.css"
    print("OK base.html wires assets")

def _check_tables_opted_in() -> list[str]:
    offenders = []
    for tpl in TEMPLATES.glob("*.html"):
        if tpl.name in ALLOWLIST:
            continue
        html = tpl.read_text(encoding="utf-8")
        for m in re.finditer(r"<table\b[^>]*>", html):
            if "data-table-tools" not in m.group(0):
                offenders.append(f"{tpl.name}: {m.group(0)[:60]}")
    return offenders

def main() -> int:
    _check_assets()
    _check_base_wires()
    offenders = _check_tables_opted_in()
    if offenders:
        print("Tables NOT opted into table-tools (add data-table-tools or ALLOWLIST):")
        for o in offenders:
            print("  -", o)
        return 1
    print("OK all tables opted in")
    print("ALL OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())
