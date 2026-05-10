"""Project-aware plans parser. Lean: list plan markdown files + simple progress %.

Progress is computed by counting checkbox markers in body:
- `- [x]` or `- [X]` -> done
- `- [ ]` -> pending
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_DONE_RE = re.compile(r"^\s*-\s*\[[xX]\]", re.MULTILINE)
_TODO_RE = re.compile(r"^\s*-\s*\[ \]", re.MULTILINE)


@dataclass
class PlanItem:
    path: str
    name: str
    title: str
    status: str
    done: int
    todo: int
    progress_pct: int
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


def list_plans(plans_dir: str) -> list[PlanItem]:
    p = Path(plans_dir)
    if not p.exists() or not p.is_dir():
        return []
    items: list[PlanItem] = []
    for f in sorted(p.glob("*.md")):
        if f.name.startswith("_"):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        body = _FRONTMATTER_RE.sub("", text, count=1)
        done = len(_DONE_RE.findall(body))
        todo = len(_TODO_RE.findall(body))
        total = done + todo
        progress_pct = (done * 100 // total) if total else 0
        items.append(PlanItem(
            path=str(f),
            name=f.stem,
            title=fm.get("title") or f.stem,
            status=fm.get("status") or ("done" if (total and todo == 0) else "active"),
            done=done, todo=todo, progress_pct=progress_pct,
            raw_frontmatter=fm,
        ))
    return items
