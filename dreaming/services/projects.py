"""Projects registry service: CRUD + filesystem scan."""
from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dreaming.services.db import SqliteDB


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Project:
    id: int
    slug: str
    label: str
    working_dir: str
    enabled: bool
    is_default: bool
    sort_order: int
    color: Optional[str]
    created_at: str
    updated_at: str


def _row_to_project(row) -> Project:
    return Project(
        id=row["id"],
        slug=row["slug"],
        label=row["label"],
        working_dir=row["working_dir"],
        enabled=bool(row["enabled"]),
        is_default=bool(row["is_default"]),
        sort_order=row["sort_order"],
        color=row["color"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ProjectsService:
    def __init__(self, db: SqliteDB):
        self.db = db

    async def list_all(self, only_enabled: bool = False) -> list[Project]:
        sql = "SELECT * FROM projects"
        if only_enabled:
            sql += " WHERE enabled=1"
        sql += " ORDER BY sort_order, slug"
        rows = await self.db.fetch_all(sql)
        return [_row_to_project(r) for r in rows]

    async def get_by_slug(self, slug: str) -> Optional[Project]:
        row = await self.db.fetch_one("SELECT * FROM projects WHERE slug=?", (slug,))
        return _row_to_project(row) if row else None

    async def get_by_id(self, project_id: int) -> Optional[Project]:
        row = await self.db.fetch_one("SELECT * FROM projects WHERE id=?", (project_id,))
        return _row_to_project(row) if row else None

    async def get_default(self) -> Optional[Project]:
        row = await self.db.fetch_one(
            "SELECT * FROM projects WHERE is_default=1 AND enabled=1 LIMIT 1")
        return _row_to_project(row) if row else None

    async def create(
        self, slug: str, label: str, working_dir: str,
        enabled: bool = True, is_default: bool = False,
        sort_order: int = 0, color: Optional[str] = None,
    ) -> Project:
        ts = _now()
        await self.db.execute(
            """INSERT INTO projects
               (slug, label, working_dir, enabled, is_default, sort_order, color, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (slug, label, working_dir, int(enabled), int(is_default),
             sort_order, color, ts, ts),
        )
        proj = await self.get_by_slug(slug)
        assert proj is not None
        return proj

    async def update(self, project_id: int, **kwargs) -> None:
        if not kwargs:
            return
        allowed = {"slug", "label", "working_dir", "enabled", "is_default", "sort_order", "color"}
        sets, params = [], []
        for k, v in kwargs.items():
            if k not in allowed:
                continue
            if k in ("enabled", "is_default"):
                v = int(bool(v))
            sets.append(f"{k}=?")
            params.append(v)
        if not sets:
            return
        sets.append("updated_at=?")
        params.append(_now())
        params.append(project_id)
        await self.db.execute(
            f"UPDATE projects SET {', '.join(sets)} WHERE id=?", tuple(params))

    async def delete(self, project_id: int) -> None:
        await self.db.execute("DELETE FROM projects WHERE id=?", (project_id,))

    async def set_setting(self, project_id: int, key: str, value) -> None:
        await self.db.execute(
            """INSERT INTO project_settings (project_id, key, value)
               VALUES (?, ?, ?)
               ON CONFLICT(project_id, key) DO UPDATE SET value=excluded.value""",
            (project_id, key, json.dumps(value)),
        )

    async def unset_setting(self, project_id: int, key: str) -> None:
        await self.db.execute(
            "DELETE FROM project_settings WHERE project_id=? AND key=?",
            (project_id, key))

    async def get_setting(self, project_id: int, key: str):
        row = await self.db.fetch_one(
            "SELECT value FROM project_settings WHERE project_id=? AND key=?",
            (project_id, key))
        return json.loads(row["value"]) if row else None

    async def all_settings(self, project_id: int) -> dict:
        rows = await self.db.fetch_all(
            "SELECT key, value FROM project_settings WHERE project_id=?",
            (project_id,))
        return {r["key"]: json.loads(r["value"]) for r in rows}

    @staticmethod
    def scan_projects_root(root: str) -> list[dict]:
        """List immediate subdirectories. Returns dicts with suggested slug, label, has_claude."""
        p = Path(root)
        if not p.exists() or not p.is_dir():
            return []
        out = []
        for entry in sorted(p.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue
            has_claude = (entry / ".claude").is_dir()
            out.append({
                "path": str(entry),
                "name": entry.name,
                "suggested_slug": entry.name,
                "suggested_label": entry.name,
                "has_claude": has_claude,
            })
        return out

    async def import_from_scan(
        self, items: list[dict], default_slug: Optional[str] = None,
    ) -> list[Project]:
        """Idempotent: skip items whose slug OR working_dir already exists.
        Re-running setup with the same projects_root is a no-op (safe to retry
        after partial failure)."""
        existing_projects = await self.list_all()
        existing_slugs = {p.slug for p in existing_projects}
        existing_paths = {p.working_dir for p in existing_projects}
        seen_in_batch_paths: set[str] = set()
        created: list[Project] = []
        for it in items:
            wd = it["working_dir"]
            if wd in existing_paths or wd in seen_in_batch_paths:
                continue
            seen_in_batch_paths.add(wd)

            slug = it["slug"]
            base = slug
            n = 1
            while slug in existing_slugs:
                n += 1
                slug = f"{base}-{n}"
            existing_slugs.add(slug)

            proj = await self.create(
                slug=slug,
                label=it.get("label", slug),
                working_dir=wd,
                enabled=bool(it.get("enabled", True)),
                is_default=(slug == default_slug),
            )
            created.append(proj)
        return created
