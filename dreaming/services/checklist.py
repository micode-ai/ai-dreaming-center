"""Parser for _weekly-learning-checklist.md (ported verbatim from ALC).

Public API:
    parse_checklist(agents_dir: str) -> tuple[str, list[ChecklistTopic]]
        Reads {agents_dir}/lessons/_weekly-learning-checklist.md and returns
        (week_label, topics).

    parse_weekly_checklist(text: str) -> list[ChecklistTopic]
        Parses raw markdown text — convenience wrapper used by the project
        topics page where the file path is resolved by the caller.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


@dataclass
class ChecklistTopic:
    number: int
    title: str
    module: str = ""
    target_agents: list[str] = field(default_factory=list)
    question: str = ""
    why_important: str = ""
    completed: bool = False


# Section titles that are not per-agent topic buckets and must be skipped.
_SKIP_SECTIONS = {
    "приоритет недели",
    "приоритет недели (рекомендация тимура)",
    "общие",
    "общие (любой агент)",
}


def _extract_week(text: str) -> str:
    """Week label: YAML frontmatter `week:` first, otherwise `# ... — Wxx` H1."""
    fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if fm_match:
        try:
            fm = yaml.safe_load(fm_match.group(1))
            if isinstance(fm, dict) and fm.get("week"):
                return str(fm["week"])
        except yaml.YAMLError:
            pass
    h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if h1:
        m = re.search(r"W\d+(?:\s*\([^)]+\))?", h1.group(1))
        if m:
            return m.group(0)
    return ""


def _is_agent_section(header: str) -> bool:
    """A `## ...` header is an agent bucket unless it matches a skip phrase."""
    normalized = header.strip().lower().rstrip(":")
    if normalized in _SKIP_SECTIONS:
        return False
    for skip in _SKIP_SECTIONS:
        if normalized.startswith(skip):
            return False
    return True


def parse_weekly_checklist(text: str) -> list[ChecklistTopic]:
    """Parse weekly learning checklist from raw markdown text.

    Expected format:

        ## <agent-name>
        - тема 1
        - тема 2

        ## <другой-агент>
        - тема

    Sections like `## Приоритет недели` or `## Общие (любой агент)` are skipped.
    Returns topics with sequential numbering from 1.
    """
    topics: list[ChecklistTopic] = []
    current_agent: str | None = None
    number = 0

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        h2 = re.match(r"^##\s+(.+?)\s*$", line)
        if h2:
            header = h2.group(1).strip()
            current_agent = header if _is_agent_section(header) else None
            continue
        if line.startswith("# ") or line.startswith("### "):
            current_agent = None if line.startswith("### ") else current_agent
            continue
        if current_agent is None:
            continue

        bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
        if not bullet:
            continue
        title = bullet.group(1).strip()
        if not title:
            continue
        number += 1
        topics.append(ChecklistTopic(
            number=number,
            title=title,
            target_agents=[current_agent],
        ))

    return topics


def parse_checklist(agents_dir: str) -> tuple[str, list[ChecklistTopic]]:
    """Parse weekly learning checklist from agents/lessons/ directory.

    Returns (week_label, topics) with sequential numbering from 1.
    """
    checklist_path = Path(agents_dir) / "lessons" / "_weekly-learning-checklist.md"
    if not checklist_path.exists():
        log.warning("Checklist not found: %s", checklist_path)
        return "", []
    text = checklist_path.read_text(encoding="utf-8")
    return _extract_week(text), parse_weekly_checklist(text)
