"""Loop templates CRUD — markdown files with YAML frontmatter."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


@dataclass
class LoopTemplate:
    slug: str
    name: str
    description: str = ""
    engine: str = "loop"            # loop | cascade | oneshot
    preset: str = ""
    max_iterations: int | None = None
    tags: list[str] = field(default_factory=list)
    agents: list[dict[str, str]] = field(default_factory=list)  # [{role, name}]
    agent: str = ""                 # single agent shortcut
    team: str = "auto"              # 'auto' | '' | name
    placeholders: list[dict[str, str]] = field(default_factory=list)  # [{key,label,default}]
    body: str = ""
    path: str = ""

    def to_frontmatter(self) -> dict[str, Any]:
        fm: dict[str, Any] = {
            "name": self.name,
            "slug": self.slug,
            "engine": self.engine,
            "description": self.description,
        }
        if self.preset:
            fm["preset"] = self.preset
        if self.max_iterations is not None:
            fm["max_iterations"] = self.max_iterations
        if self.tags:
            fm["tags"] = self.tags
        if self.agents:
            fm["agents"] = self.agents
        elif self.agent:
            fm["agent"] = self.agent
        else:
            fm["team"] = self.team
        if self.placeholders:
            fm["placeholders"] = self.placeholders
        return fm


def list_templates(templates_dir: str) -> list[LoopTemplate]:
    base = Path(templates_dir)
    if not base.exists():
        return []
    out: list[LoopTemplate] = []
    for p in sorted(base.glob("*.md")):
        tpl = _read_file(p)
        if tpl:
            out.append(tpl)
    return out


def read_template(templates_dir: str, slug: str) -> LoopTemplate | None:
    base = Path(templates_dir)
    p = base / f"{slug}.md"
    if not p.exists():
        return None
    return _read_file(p)


def write_template(templates_dir: str, tpl: LoopTemplate) -> Path:
    base = Path(templates_dir)
    base.mkdir(parents=True, exist_ok=True)
    p = base / f"{tpl.slug}.md"
    fm_yaml = yaml.safe_dump(tpl.to_frontmatter(), allow_unicode=True, sort_keys=False).strip()
    body = tpl.body.strip()
    p.write_text(f"---\n{fm_yaml}\n---\n\n{body}\n", encoding="utf-8")
    return p


def delete_template(templates_dir: str, slug: str) -> bool:
    p = Path(templates_dir) / f"{slug}.md"
    if not p.exists():
        return False
    p.unlink()
    return True


def _read_file(path: Path) -> LoopTemplate | None:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except Exception as e:
        log.warning("template read error %s: %s", path, e)
        return None
    m = _FRONTMATTER_RE.match(text)
    if not m:
        log.warning("template missing frontmatter: %s", path)
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception as e:
        log.warning("template yaml parse error %s: %s", path, e)
        return None
    body = m.group(2).strip()
    return LoopTemplate(
        slug=str(fm.get("slug") or path.stem),
        name=str(fm.get("name") or path.stem),
        description=str(fm.get("description") or ""),
        engine=str(fm.get("engine") or "loop"),
        preset=str(fm.get("preset") or ""),
        max_iterations=fm.get("max_iterations"),
        tags=list(fm.get("tags") or []),
        agents=list(fm.get("agents") or []),
        agent=str(fm.get("agent") or ""),
        team=str(fm.get("team") or "auto"),
        placeholders=list(fm.get("placeholders") or []),
        body=body,
        path=str(path.resolve()),
    )
