"""GET /p/{slug}/wiki-health — per-project wiki trends & coverage.

Reads from the resolved per-project `wiki_dir` (default `docs/wiki`). The
trends file is looked up in a couple of conventional places:
  1. <wiki_dir>/wiki-health-trends.md            (flat layout)
  2. <wiki_dir>/reports/wiki-health-trends.md    (with-reports layout)
  3. <wiki_dir>/03-Team/reports/wiki-health-trends.md (Obsidian convention)

If none exist we still show coverage counts and a friendly empty-state
pointing at the wiki_dir we resolved (and where to put the trends file).
"""
from __future__ import annotations
import re
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


_SECTION_RE = re.compile(r"^##\s+(.+?)\s*\((\d{4}-\d{2}-\d{2})\)\s*$", re.MULTILINE)
_METRIC_RE = re.compile(
    r"^- `(?P<key>[a-z_]+)`:\s*(?P<value>[^\n—]+?)(?:\s+—|$)",
    re.MULTILINE,
)


def _parse_value(raw: str) -> Any:
    raw = raw.strip()
    if raw.lower() in ("n/a", "none", "—"):
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    m = re.match(r"^([\d.]+)", raw)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return raw


def _parse_trends(text: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    matches = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        metrics: dict[str, Any] = {}
        for mm in _METRIC_RE.finditer(body):
            metrics[mm.group("key")] = _parse_value(mm.group("value"))
        sections.append({
            "label": m.group(1).strip(),
            "date": m.group(2).strip(),
            "metrics": metrics,
        })
    sections.sort(key=lambda s: s["date"])
    return sections


def _resolve_wiki_dir(working_dir: str | None, wiki_dir_setting: str) -> Path | None:
    """`wiki_dir_setting` can be absolute or relative-to-working_dir."""
    if not wiki_dir_setting:
        return None
    p = Path(wiki_dir_setting)
    if p.is_absolute():
        return p
    if not working_dir:
        return None
    return Path(working_dir) / p


def _trends_candidates(wiki_root: Path) -> list[Path]:
    """Conventional locations where wiki-health-trends.md might live."""
    return [
        wiki_root / "wiki-health-trends.md",
        wiki_root / "reports" / "wiki-health-trends.md",
        wiki_root / "03-Team" / "reports" / "wiki-health-trends.md",
    ]


def _coverage_snapshot(wiki_root: Path | None) -> dict[str, int]:
    """Count covered modules and learning notes inside `wiki_root`.

    Covered = any `.md` file at the wiki root (or inside `domains/` for
    the modular layout). Learning notes = files under `learning/` if it
    exists. Both are best-effort heuristics; the original counted only
    `<vault>/04-Knowledge/modules/<x>/<x>.md` pairs."""
    out = {"covered": 0, "learning_notes": 0}
    if wiki_root is None or not wiki_root.exists():
        return out
    domains = wiki_root / "domains"
    if domains.is_dir():
        out["covered"] = sum(1 for _ in domains.glob("*.md"))
    else:
        # Flat layout — count top-level .md files (excluding README/INDEX).
        out["covered"] = sum(
            1 for p in wiki_root.glob("*.md")
            if p.stem.lower() not in ("readme", "index")
        )
    learning = wiki_root / "learning"
    if learning.is_dir():
        out["learning_notes"] = sum(1 for _ in learning.rglob("*.md"))
    return out


@router.get("/p/{slug}/wiki-health")
async def project_wiki_health(request: Request, slug: str):
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    wiki_dir_setting = await resolver.get(project, "wiki_dir", "docs/wiki")
    wiki_root = _resolve_wiki_dir(project.working_dir, wiki_dir_setting)

    series: list[dict[str, Any]] = []
    error: str | None = None
    trends_path: Path | None = None

    if wiki_root is None:
        error = "wiki_dir не настроен и working_dir пуст — заполните настройки проекта."
    elif not wiki_root.exists():
        error = f"Каталог вики не найден: {wiki_root}. Проверьте wiki_dir."
    else:
        for cand in _trends_candidates(wiki_root):
            if cand.exists():
                trends_path = cand
                break
        if trends_path is None:
            error = (
                f"Файл трендов не найден. Положите его сюда: "
                f"{wiki_root / 'wiki-health-trends.md'}"
            )
        else:
            try:
                series = _parse_trends(trends_path.read_text(encoding="utf-8"))
            except Exception as e:
                error = f"Ошибка парсинга {trends_path}: {type(e).__name__}: {e}"

    snapshot = _coverage_snapshot(wiki_root)
    latest = series[-1] if series else None
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    projects = await request.app.state.projects.list_all(only_enabled=True)
    return request.app.state.templates.TemplateResponse(
        request,
        "project_wiki_health.html",
        {
            "project": project,
            "series": series,
            "snapshot": snapshot,
            "latest": latest,
            "error": error,
            "wiki_root": str(wiki_root) if wiki_root else "",
            "trends_path": str(trends_path) if trends_path else (
                str(wiki_root / "wiki-health-trends.md") if wiki_root else ""
            ),
            "today": date.today().isoformat(),
            "projects": projects,
            "locale": locale,
        },
    )
