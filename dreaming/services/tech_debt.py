"""Parser for tech-debt items (TD-*.md files with YAML frontmatter).

Project-aware port of ALC's app/services/tech_debt.py: every public function
takes the tech-debt directory as its first argument instead of reading from a
global settings object. The dataclass for items is defined inline so the service
has no `app.*` dependencies.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


@dataclass
class TechDebtItem:
    id: str = ""
    title: str = ""
    status: str = "open"
    priority: str = "P2"
    module: str = ""
    created: str = ""
    created_by: str = ""
    source: str = ""
    complexity: str = ""
    autonomy: str = ""
    confidence: str = ""
    release: str = ""
    jira: str | None = None
    closed_at: str = ""
    verified_at: str = ""
    closed_by: str = ""
    blocked_by: list[str] = field(default_factory=list)
    contract: str = ""
    file_path: str = ""


@dataclass
class ReleaseItem:
    release: str = ""
    target_date: str = ""
    status: str = ""
    description: str = ""
    file_path: str = ""


def _norm_date(v) -> str:
    """YAML date -> 'YYYY-MM-DD'; None/null/'' -> ''. Handles date, datetime, str."""
    if v in (None, "", "null"):
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()[:10]
    return str(v).strip()


def _norm_list(v) -> list[str]:
    """Normalise YAML list field. Accepts list, comma-string, None."""
    if not v:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if x not in (None, "", "null")]
    if isinstance(v, str):
        return [p.strip() for p in v.split(",") if p.strip()]
    return []


def _iter_td_paths(tech_debt_dir: str):
    """Yield TD-*.md paths.

    Looks first under {tech_debt_dir}/items (ALC layout); if absent, falls back
    to scanning {tech_debt_dir} itself (flat layout common in micode projects).
    """
    base = Path(tech_debt_dir)
    items_dir = base / "items"
    if items_dir.exists():
        yield from sorted(items_dir.glob("TD-*.md"))
        return
    if base.exists():
        # Accept both TD-prefixed files and any *.md so the smoke-test case
        # (single TD-001.md at the root) and the canonical layout both work.
        seen: set[Path] = set()
        for p in sorted(base.glob("TD-*.md")):
            seen.add(p)
            yield p
        for p in sorted(base.glob("*.md")):
            if p not in seen:
                yield p


def parse_tech_debt(tech_debt_dir: str) -> list[TechDebtItem]:
    """Parse all TD-*.md files from the tech debt directory."""
    items: list[TechDebtItem] = []
    for path in _iter_td_paths(tech_debt_dir):
        try:
            text = path.read_text(encoding="utf-8-sig")  # BOM-safe
            if not text.startswith("---"):
                continue
            end = text.find("\n---", 3)
            if end < 0:
                continue
            fm_text = text[3:end].strip()
            fm = yaml.safe_load(fm_text)
            if not fm or not isinstance(fm, dict):
                continue

            jira = fm.get("jira")
            if jira in (None, "", "null"):
                jira = None
            else:
                jira = str(jira)

            items.append(TechDebtItem(
                id=str(fm.get("id", "")),
                title=fm.get("title", path.stem),
                status=fm.get("status", "open"),
                priority=fm.get("priority", "P2"),
                module=fm.get("module", ""),
                created=str(fm.get("created", "")),
                created_by=fm.get("created_by", ""),
                source=fm.get("source", ""),
                complexity=str(fm.get("complexity", "")),
                autonomy=str(fm.get("autonomy", "")),
                confidence=str(fm.get("confidence", "")),
                release=str(fm.get("release", "")),
                jira=jira,
                closed_at=_norm_date(fm.get("closed_at")),
                verified_at=_norm_date(fm.get("verified_at")),
                closed_by=str(fm.get("closed_by") or ""),
                blocked_by=_norm_list(fm.get("blocked_by")),
                contract=str(fm.get("contract") or ""),
                file_path=str(path.resolve()),
            ))
        except Exception as e:
            log.warning("Error parsing %s: %s", path.name, e)

    return items


def list_tech_debt(tech_debt_dir: str) -> list[TechDebtItem]:
    """Public reader used by the Wave 2 routes — alias for parse_tech_debt."""
    return parse_tech_debt(tech_debt_dir)


def read_tech_debt_item(tech_debt_dir: str, item_id: str) -> TechDebtItem | None:
    """Find and return a single TD item by id, or None."""
    for item in parse_tech_debt(tech_debt_dir):
        if item.id == item_id:
            return item
    return None


def parse_releases(tech_debt_dir: str) -> list[ReleaseItem]:
    """Parse {td_dir}/releases/R*.md files (non-recursive, excludes archive/)."""
    releases_dir = Path(tech_debt_dir) / "releases"
    if not releases_dir.exists():
        return []

    out: list[ReleaseItem] = []
    for path in releases_dir.glob("R*.md"):
        try:
            text = path.read_text(encoding="utf-8-sig")
            if not text.startswith("---"):
                continue
            end = text.find("\n---", 3)
            if end < 0:
                continue
            fm = yaml.safe_load(text[3:end].strip()) or {}
            if not isinstance(fm, dict):
                continue

            out.append(ReleaseItem(
                release=str(fm.get("release") or path.stem),
                target_date=_norm_date(fm.get("target_date")),
                status=str(fm.get("status") or ""),
                description=str(fm.get("description") or ""),
                file_path=str(path.resolve()),
            ))
        except Exception as e:
            log.warning("Error parsing release %s: %s", path.name, e)

    out.sort(key=lambda r: (r.target_date or "9999", r.release))
    return out


def find_td_file(tech_debt_dir: str, td_id: str) -> Path | None:
    """Find a TD-*.md file by id (TD-NNN). Returns first match or None."""
    items_dir = Path(tech_debt_dir) / "items"
    search_dir = items_dir if items_dir.exists() else Path(tech_debt_dir)
    if not search_dir.exists():
        return None
    matches = list(search_dir.glob(f"{td_id}-*.md")) + list(search_dir.glob(f"{td_id}.md"))
    return matches[0] if matches else None


def read_td(file_path: str) -> tuple[dict, str]:
    """Read a single TD-*.md file. Returns (frontmatter_dict, body_text).

    Body is returned as raw markdown — callers can render to HTML if needed.
    Wave 2.2 doesn't need HTML rendering so we avoid the markdown dep.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"TD file not found: {file_path}")

    text = path.read_text(encoding="utf-8-sig")
    meta: dict = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            try:
                meta = yaml.safe_load(text[3:end].strip()) or {}
                if not isinstance(meta, dict):
                    meta = {}
            except yaml.YAMLError:
                meta = {}
            body = text[end + 4:].lstrip("\n")

    return meta, body
