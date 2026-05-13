"""GET /p/{slug}/wiki-health — per-project wiki trends & coverage.

Parses `<working_dir>/docs/wiki/wiki-health-trends.md` (ALC convention) into
time-series JSON, and renders a Chart.js page. If the file is missing we
show graceful empty state with the resolved path.
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


def _trends_path(working_dir: str | None) -> Path | None:
    if not working_dir:
        return None
    p = Path(working_dir) / "docs" / "wiki" / "wiki-health-trends.md"
    return p


def _modules_snapshot(working_dir: str | None) -> dict[str, int]:
    out = {"covered": 0, "learning_notes": 0}
    if not working_dir:
        return out
    wiki = Path(working_dir) / "docs" / "wiki"
    if not wiki.exists():
        return out
    out["covered"] = sum(1 for d in wiki.iterdir() if d.is_dir())
    learning = wiki / "learning"
    if learning.exists():
        out["learning_notes"] = sum(1 for _ in learning.rglob("*.md"))
    return out


@router.get("/p/{slug}/wiki-health")
async def project_wiki_health(request: Request, slug: str):
    project = request.state.project
    path = _trends_path(project.working_dir)
    series: list[dict[str, Any]] = []
    error: str | None = None
    if not path:
        error = "Проект без working_dir — невозможно найти trends-файл."
    elif not path.exists():
        error = f"Файл не найден: {path}. Создайте его в docs/wiki/."
    else:
        try:
            series = _parse_trends(path.read_text(encoding="utf-8"))
        except Exception as e:
            error = f"Ошибка парсинга: {type(e).__name__}: {e}"

    snapshot = _modules_snapshot(project.working_dir)
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
            "trends_path": str(path) if path else "",
            "today": date.today().isoformat(),
            "projects": projects,
            "locale": locale,
        },
    )
