"""Smoke check for Wave C tech-debt view upgrade.

Verifies:
  - Templates parse syntactically (with a stubbed `t` filter)
  - tech_debt parser exposes all fields the new template renders

Run: python scripts/smoke_tech_debt_view.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def smoke_templates_parse():
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader("dreaming/templates"))
    env.filters["t"] = lambda k, **kw: k
    env.get_template("project_findings.html")
    env.get_template("project_findings_detail.html")
    print("  [OK] templates parse")


def smoke_parser_exposes_fields():
    from dreaming.services.tech_debt import parse_tech_debt
    tmp = Path(tempfile.mkdtemp(prefix="dc_smoke_td_view_"))
    try:
        items_dir = tmp / "items"
        items_dir.mkdir()
        fixture = items_dir / "TD-smoke.md"
        fixture.write_text(
            "---\n"
            "id: TD-smoke\n"
            "title: Smoke test finding\n"
            "status: open\n"
            "priority: high\n"
            "module: smoke\n"
            "created: 2026-05-20\n"
            "complexity: M\n"
            "autonomy: high\n"
            "confidence: medium\n"
            "---\n\n"
            "Body content.\n",
            encoding="utf-8",
        )
        items = parse_tech_debt(str(tmp))
        assert len(items) == 1, f"expected 1 item, got {len(items)}"
        it = items[0]
        for field in ("id", "title", "status", "priority", "module",
                      "complexity", "autonomy", "confidence", "created"):
            v = getattr(it, field, None)
            assert v, f"field {field!r} missing or empty (got {v!r})"
        print("  [OK] parse_tech_debt exposes complexity/autonomy/confidence/created")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    smoke_templates_parse()
    smoke_parser_exposes_fields()
    print("smoke_tech_debt_view OK")


if __name__ == "__main__":
    main()
