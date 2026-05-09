"""Wave 2 smoke: pipelines parsers + routes empty/populated states."""
import asyncio
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def http_get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def main() -> int:
    base = "http://localhost:8086"

    # Empty states
    for path in ("topics", "kanban", "notes", "findings", "tech-debt", "ideas", "wiki"):
        code, body = http_get(f"{base}/p/test/{path}")
        assert code == 200, f"/{path} returned {code}"
    print("All 7 routes return 200 in empty state")

    # DB direct: add a custom topic via service, then check it appears on /kanban
    from dreaming.services.db import SqliteDB
    from dreaming.services.projects import ProjectsService

    async def go():
        db = SqliteDB("data/dreaming.db"); await db.connect()
        try:
            svc = ProjectsService(db)
            proj = await svc.get_by_slug("test")
            tid = await db.add_custom_topic(proj.id, "Smoke W2 topic", module="x")
            return tid
        finally:
            await db.close()

    tid = asyncio.run(go())
    code, body = http_get(f"{base}/p/test/kanban")
    assert "Smoke W2 topic" in body, "kanban does not show added topic"
    print(f"Kanban shows newly added topic (id={tid[:8]}...)")

    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
