"""Wave 0 end-to-end smoke: scan + import all projects under projects_root.
Asserts DB has the expected count after import. Idempotent (safe to re-run)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services.db import SqliteDB
from dreaming.services.projects import ProjectsService


PROJECTS_ROOT = r"D:\Work\micode"
DB_PATH = "data/dreaming.db"


async def main() -> int:
    db = SqliteDB(DB_PATH)
    await db.connect()
    try:
        svc = ProjectsService(db)
        scan = svc.scan_projects_root(PROJECTS_ROOT)
        print(f"Scanned: {len(scan)} dirs")
        items = [
            {"slug": s["suggested_slug"], "label": s["suggested_label"],
             "working_dir": s["path"], "enabled": True}
            for s in scan
        ]
        before = await svc.list_all()
        created = await svc.import_from_scan(items, default_slug=items[0]["slug"] if items else None)
        after = await svc.list_all()
        print(f"Before: {len(before)}; created in this run: {len(created)}; after: {len(after)}")
        # Idempotency check: re-running must not create more rows
        again = await svc.import_from_scan(items)
        final = await svc.list_all()
        assert len(final) == len(after), \
            f"Import not idempotent: {len(after)} -> {len(final)}"
        print(f"After idempotency re-run: {len(final)} (unchanged OK)")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
