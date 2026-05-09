"""Smoke check: scan projects_root and list discovered dirs."""
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services.db import SqliteDB
from dreaming.services.projects import ProjectsService


async def main() -> int:
    db = SqliteDB("data/dreaming.db")
    await db.connect()
    try:
        items = ProjectsService.scan_projects_root(r"D:\Work\micode")
        print(f"Found {len(items)} dirs")
        for it in items:
            print(f"  {it['name']:30} has_claude={it['has_claude']}")
        return 0 if items else 1
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
