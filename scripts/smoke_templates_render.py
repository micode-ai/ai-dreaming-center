"""Compile every Jinja template; then best-effort GET every simple route.

Tier 1 (deterministic, always runs): compile all *.html under
dreaming/templates through a Jinja environment matching the app's. Catches the
failure mode this design wave risks -- a syntax typo introduced while bulk
editing 51 templates. Does NOT catch runtime errors (undefined variable, bad
filter argument).

Tier 2 (best effort): boot the app through its real lifespan and GET every
registered GET route that needs no path parameter other than a project slug.
Skipped with a printed notice when no project is configured, so the script
stays useful on a fresh checkout.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TEMPLATES = ROOT / "dreaming" / "templates"

# SSE endpoints never complete -- a plain GET would hang the run.
SSE = re.compile(r"/stream(/|$)")


def compile_all() -> int:
    from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError

    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    env.filters["t"] = lambda k, **kw: k  # runtime filter; stubbed for compile

    failures: list[str] = []
    names = sorted(p.relative_to(TEMPLATES).as_posix() for p in TEMPLATES.rglob("*.html"))
    for name in names:
        try:
            env.get_template(name)
        except TemplateSyntaxError as exc:
            failures.append(f"  {name}:{exc.lineno}: {exc.message}")

    if failures:
        print(f"Template compile FAILED ({len(failures)} of {len(names)}):")
        print("\n".join(failures))
        return 1
    print(f"OK all {len(names)} templates compile")
    return 0


def walk_routes() -> int:
    try:
        from fastapi.testclient import TestClient
        from dreaming.main import app
    except Exception as exc:  # noqa: BLE001 - environment issue, not a failure
        print(f"SKIP route walk (cannot import app: {exc})")
        return 0

    with TestClient(app) as client:
        slug = None
        try:
            rows = client.get("/projects")
            if rows.status_code == 200:
                m = re.search(r'name="slug" value="([a-z0-9-]+)"', rows.text)
                slug = m.group(1) if m else None
        except Exception:  # noqa: BLE001
            slug = None

        if not slug:
            print("SKIP route walk (no project configured in the local DB)")
            return 0
        print(f"Route walk using project slug: {slug}")

        paths: list[str] = []
        for route in app.routes:
            methods = getattr(route, "methods", None) or set()
            path = getattr(route, "path", "")
            if "GET" not in methods or not path:
                continue
            if SSE.search(path):
                continue
            candidate = path.replace("{slug}", slug)
            if "{" in candidate:  # needs an id we do not have
                continue
            paths.append(candidate)

        bad: list[str] = []
        for path in sorted(set(paths)):
            try:
                r = client.get(path, follow_redirects=True)
            except Exception as exc:  # noqa: BLE001
                bad.append(f"  {path}: raised {type(exc).__name__}: {exc}")
                continue
            if r.status_code >= 500:
                bad.append(f"  {path}: HTTP {r.status_code}")

        if bad:
            print(f"Route walk FAILED ({len(bad)} of {len(set(paths))}):")
            print("\n".join(bad))
            return 1
        print(f"OK all {len(set(paths))} parameter-free GET routes render")
    return 0


def main() -> int:
    rc = compile_all()
    rc |= walk_routes()
    print("FAIL" if rc else "ALL OK")
    return rc


if __name__ == "__main__":
    sys.exit(main())
