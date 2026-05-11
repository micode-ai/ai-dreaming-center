"""Parser for product-idea items (PI-*.md files with YAML frontmatter).

Project-aware port of ALC's app/services/product_ideas.py: every public function
takes the product-ideas directory as its first argument instead of reading from a
global settings object. The dataclass for items is defined inline so the service
has no `app.*` dependencies.

Wave 2 lean — just enumerate items with their frontmatter; deeper functionality
(read/edit) arrives in later waves.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


@dataclass
class ProductIdeaItem:
    id: str = ""
    title: str = ""
    status: str = "new"
    impact: str = "medium"
    effort: str = "M"
    confidence: str = "medium"
    priority: str = ""
    module: str = ""
    user_segment: str = ""
    competitor: str = ""
    source: str = ""
    source_agent: str = ""
    created: str = ""
    target_release: str = "unassigned"
    jira_epic: str | None = None
    jira_task: str | None = None
    jira_ticket: str | None = None
    github_issue: str | None = None
    orchestration_run: str | None = None
    value_hypothesis: str = ""
    file_path: str = ""


def _iter_pi_paths(product_ideas_dir: str):
    """Yield PI-*.md paths.

    Looks first under {product_ideas_dir}/items (ALC layout); if absent, falls
    back to scanning {product_ideas_dir} itself (flat layout common in micode
    projects). Mirrors the tech-debt resolver pattern.
    """
    base = Path(product_ideas_dir)
    items_dir = base / "items"
    if items_dir.exists():
        yield from sorted(items_dir.glob("PI-*.md"))
        return
    if base.exists():
        seen: set[Path] = set()
        for p in sorted(base.glob("PI-*.md")):
            seen.add(p)
            yield p
        for p in sorted(base.glob("*.md")):
            if p not in seen:
                yield p


def list_product_ideas(product_ideas_dir: str) -> list[ProductIdeaItem]:
    """Parse all PI-*.md files from the product-ideas directory."""
    items: list[ProductIdeaItem] = []
    for path in _iter_pi_paths(product_ideas_dir):
        try:
            text = path.read_text(encoding="utf-8-sig")
            if not text.startswith("---"):
                continue
            end = text.find("\n---", 3)
            if end < 0:
                continue
            fm_text = text[3:end].strip()
            fm = yaml.safe_load(fm_text)
            if not fm or not isinstance(fm, dict):
                continue

            jira_epic = fm.get("jira_epic")
            if jira_epic in (None, "", "null"):
                jira_epic = None
            else:
                jira_epic = str(jira_epic)

            jira_task = fm.get("jira_task")
            if jira_task in (None, "", "null"):
                jira_task = None
            else:
                jira_task = str(jira_task)

            jira_ticket = fm.get("jira_ticket")
            if jira_ticket in (None, "", "null"):
                jira_ticket = None
            else:
                jira_ticket = str(jira_ticket)

            github_issue = fm.get("github_issue")
            if github_issue in (None, "", "null"):
                github_issue = None
            else:
                github_issue = str(github_issue)

            orchestration_run = fm.get("orchestration_run")
            if orchestration_run in (None, "", "null"):
                orchestration_run = None
            else:
                orchestration_run = str(orchestration_run)

            items.append(ProductIdeaItem(
                id=str(fm.get("id", "")),
                title=str(fm.get("title", path.stem)),
                status=str(fm.get("status", "new")),
                impact=str(fm.get("impact", "medium")),
                effort=str(fm.get("effort", "M")),
                confidence=str(fm.get("confidence", "medium")),
                priority=str(fm.get("priority", "")),
                module=str(fm.get("module", "")),
                user_segment=str(fm.get("user_segment", "")),
                competitor=str(fm.get("competitor", "")),
                source=str(fm.get("source", "")),
                source_agent=str(fm.get("source_agent", "")),
                created=str(fm.get("created", "")),
                target_release=str(fm.get("target_release", "unassigned")),
                jira_epic=jira_epic,
                jira_task=jira_task,
                jira_ticket=jira_ticket,
                github_issue=github_issue,
                orchestration_run=orchestration_run,
                value_hypothesis=str(fm.get("value_hypothesis", "")),
                file_path=str(path.resolve()),
            ))
        except Exception as e:
            log.warning("Error parsing %s: %s", path.name, e)

    return items


def parse_product_ideas(product_ideas_dir: str) -> list[ProductIdeaItem]:
    """Alias kept for parity with ALC naming."""
    return list_product_ideas(product_ideas_dir)


def read_product_idea(file_path: str) -> tuple[dict, str]:
    """Read a single PI-*.md file. Returns (frontmatter_dict, body_text).

    Body is returned as raw markdown — callers can render to HTML if needed.
    Wave 2.3 doesn't need HTML rendering so we avoid the markdown dep.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PI file not found: {file_path}")

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


def read_idea_slug(file_path: str) -> str:
    """Extract slug from PI-NNN-<slug>.md filename."""
    stem = Path(file_path).stem
    m = re.match(r"^PI-\d+-(.+)$", stem)
    return m.group(1) if m else stem
