"""Smoke check for Wave F review/triage page."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def smoke_template_parses():
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader("dreaming/templates"))
    env.filters["t"] = lambda k, **kw: k
    env.get_template("project_review.html")
    print("  [OK] project_review.html parses")


def smoke_route_registered():
    import os
    import tempfile
    os.environ["DC_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="dc_smoke_review_")) / "test.db")
    from dreaming.main import app
    target = "/p/{slug}/review"
    registered = [r.path for r in app.routes if hasattr(r, "path")]
    assert target in registered, f"expected {target!r} registered, got {len(registered)} routes"
    methods = next((r.methods for r in app.routes if getattr(r, "path", None) == target), None)
    assert methods and "GET" in methods, f"expected GET on {target}, got {methods}"
    print("  [OK] /p/{slug}/review route registered (GET)")


def main():
    smoke_template_parses()
    smoke_route_registered()
    print("smoke_review OK")


if __name__ == "__main__":
    main()
