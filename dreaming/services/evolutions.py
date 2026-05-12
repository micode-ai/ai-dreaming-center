"""Project-aware evolutions parser: list markdown files in _context/ overrides dir.

Lean Wave 4 implementation — surfaces frontmatter only. Conflict-gate / reapply
logic is deferred to a later wave.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class EvolutionItem:
    path: str
    name: str
    agent_name: str
    title: str
    status: str
    has_conflict: bool
    relative_path: str = ""  # relative to evolutions_dir, for safe browser linking
    raw_frontmatter: dict[str, str] = field(default_factory=dict)


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


def list_evolutions(evolutions_dir: str) -> list[EvolutionItem]:
    p = Path(evolutions_dir)
    if not p.exists() or not p.is_dir():
        return []
    items: list[EvolutionItem] = []
    for f in sorted(p.rglob("*.md")):
        if f.name.startswith("_") or f.name.startswith("."):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        agent_name = fm.get("agent") or fm.get("agent_name") or f.parent.name or ""
        try:
            rel = str(f.relative_to(p)).replace("\\", "/")
        except ValueError:
            rel = f.name
        items.append(EvolutionItem(
            path=str(f),
            name=f.stem,
            agent_name=agent_name,
            title=fm.get("title") or f.stem,
            status=fm.get("status") or "active",
            has_conflict=bool(fm.get("conflict")),
            relative_path=rel,
            raw_frontmatter=fm,
        ))

    # Auto-detect implicit conflicts: when ≥2 non-archived evolutions target
    # the same agent, they probably need human review. Mark each as
    # conflict=true unless the file's own frontmatter explicitly says
    # `conflict: false` (which would be a deliberate "I checked, no conflict"
    # signal from the author). Frontmatter-true is always kept as-is.
    from collections import Counter
    open_statuses = {"active", "proposed", "open", ""}
    agent_counts = Counter(
        it.agent_name for it in items
        if it.status.lower() in open_statuses
    )
    for it in items:
        if (
            it.agent_name
            and it.status.lower() in open_statuses
            and agent_counts[it.agent_name] > 1
            and it.raw_frontmatter.get("conflict", "").lower() != "false"
        ):
            it.has_conflict = True
    return items
