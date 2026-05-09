"""Seed exactly one project for smoke tests that need a known slug."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services.db import SqliteDB
from dreaming.services.projects import ProjectsService


async def main(slug: str = "test", working_dir: str = r"D:\Work\micode\mi-code-ai") -> int:
    db = SqliteDB("data/dreaming.db")
    await db.connect()
    try:
        svc = ProjectsService(db)
        existing = await svc.get_by_slug(slug)
        if existing is None:
            await svc.create(slug=slug, label=slug, working_dir=working_dir)
            print(f"created {slug}")
        else:
            print(f"{slug} already exists, skipped")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(*sys.argv[1:])))
