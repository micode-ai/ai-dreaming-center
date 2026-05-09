"""Discover agents from a project's .claude/agents/ directory."""
from __future__ import annotations
from pathlib import Path


def list_agent_names(working_dir: str) -> list[str]:
    """Return agent names (basenames) found in {working_dir}/.claude/agents/.
    An agent is a .md file (single-file agent) or a directory containing
    {name}.md / agent.md (multi-file)."""
    base = Path(working_dir) / ".claude" / "agents"
    if not base.exists() or not base.is_dir():
        return []
    names: set[str] = set()
    for entry in base.iterdir():
        if entry.name.startswith("_") or entry.name.startswith("."):
            continue
        if entry.is_file() and entry.suffix == ".md":
            names.add(entry.stem)
        elif entry.is_dir():
            md = entry / f"{entry.name}.md"
            if md.exists() or (entry / "agent.md").exists():
                names.add(entry.name)
    return sorted(names)
