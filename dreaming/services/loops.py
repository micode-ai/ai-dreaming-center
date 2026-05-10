"""Project-aware loops parser. Lean Wave 4: list reflex-loop markdown files."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class LoopItem:
    path: str
    name: str
    title: str
    status: str
    iterations: int
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


def list_loops(loops_dir: str) -> list[LoopItem]:
    p = Path(loops_dir)
    if not p.exists() or not p.is_dir():
        return []
    items: list[LoopItem] = []
    for f in sorted(p.glob("*.md")):
        if f.name.startswith("_"):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        try:
            iterations = int(fm.get("iterations", "0") or 0)
        except ValueError:
            iterations = 0
        items.append(LoopItem(
            path=str(f),
            name=f.stem,
            title=fm.get("title") or f.stem,
            status=fm.get("status") or "running",
            iterations=iterations,
            raw_frontmatter=fm,
        ))
    return items
