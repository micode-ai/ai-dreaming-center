"""Project-aware contracts parser. Module/page contract markdown files in a directory.

A contract is a markdown file with frontmatter:
- kind: module | page
- module: <name>
- page: <name>  (for kind=page)
- status: draft | active | deprecated
- last_review_at: ISO date
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class ContractItem:
    path: str
    name: str
    kind: str          # 'module' | 'page' | 'unknown'
    module: str
    page: str
    status: str
    last_review_at: str
    raw_frontmatter: dict = field(default_factory=dict)


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip('"\'')
    return out


def list_contracts(contracts_dir: str) -> list[ContractItem]:
    p = Path(contracts_dir)
    if not p.exists() or not p.is_dir():
        return []
    items: list[ContractItem] = []
    for f in sorted(p.rglob("*.md")):
        if f.name.startswith("_") or f.name.startswith("."):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        items.append(ContractItem(
            path=str(f),
            name=f.stem,
            kind=fm.get("kind") or "unknown",
            module=fm.get("module") or "",
            page=fm.get("page") or "",
            status=fm.get("status") or "draft",
            last_review_at=fm.get("last_review_at") or "",
            raw_frontmatter=fm,
        ))
    return items
