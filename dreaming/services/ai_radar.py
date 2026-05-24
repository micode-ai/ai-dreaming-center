"""AI Radar — внешние сигналы индустрии ИИ (Karpathy, Anthropic, OpenAI, ...).

Wave R1 — оффлайн часть: парс watchlist-а, мердж inbox-файлов в БД,
ручной «apply» finding-а в markdown-стаб. Реальный скан (Wave R2) кладёт
inbox-файлы; реальная интеграция с idea/topic/tech-debt (Wave R3) заменит
note-стаб на вызовы соответствующих сервисов.
"""
from __future__ import annotations
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SOURCES_PATH = Path("data/ai-radar/sources.yaml")
DEFAULT_INBOX_DIR = Path("data/ai-radar/inbox")
DEFAULT_ARCHIVE_DIR = Path("data/ai-radar/archive")
DEFAULT_APPLIED_DIR = Path("data/ai-radar/applied")


@dataclass(frozen=True)
class SourceEntry:
    key: str
    kind: str  # 'person' | 'org' | 'feed' | 'paper_venue'
    name: str
    urls: dict[str, str]  # произвольные именованные ссылки (blog, x, rss, ...)
    tags: list[str]


@dataclass(frozen=True)
class Watchlist:
    sources: list[SourceEntry]

    def by_key(self, key: str) -> SourceEntry | None:
        for s in self.sources:
            if s.key == key:
                return s
        return None


def load_sources(path: str | Path = DEFAULT_SOURCES_PATH) -> Watchlist:
    """Прочитать YAML с источниками. Файла нет → пустой Watchlist (UI покажет онбординг)."""
    p = Path(path)
    if not p.exists():
        return Watchlist(sources=[])
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out: list[SourceEntry] = []
    for kind_key in ("people", "orgs", "feeds", "venues"):
        kind = {"people": "person", "orgs": "org",
                "feeds": "feed", "venues": "paper_venue"}[kind_key]
        for entry in (raw.get(kind_key) or []):
            if not isinstance(entry, dict) or "key" not in entry:
                continue
            key = str(entry["key"]).strip()
            name = str(entry.get("name", key))
            tags = list(entry.get("tags") or [])
            # Все остальные строковые поля считаем URL-ами.
            urls = {
                k: str(v) for k, v in entry.items()
                if k not in ("key", "name", "tags") and isinstance(v, str) and v
            }
            out.append(SourceEntry(key=key, kind=kind, name=name, urls=urls, tags=tags))
    return Watchlist(sources=out)


def _normalize_finding(rec: dict[str, Any], default_kind: str = "feed") -> dict | None:
    """Привести finding из inbox-JSON к колонкам ai_radar_findings. None если мусор."""
    if not isinstance(rec, dict):
        return None
    url = (rec.get("url") or "").strip()
    title = (rec.get("title") or "").strip()
    source_key = (rec.get("source_key") or "").strip()
    if not url or not title or not source_key:
        return None
    tags = rec.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    novelty = rec.get("novelty_score")
    try:
        novelty = float(novelty) if novelty is not None else None
    except (TypeError, ValueError):
        novelty = None
    relevance = rec.get("relevance_hint") or ""
    if isinstance(relevance, list):
        relevance = ",".join(str(s).strip() for s in relevance if str(s).strip())
    return {
        "source_key": source_key,
        "source_kind": rec.get("source_kind") or default_kind,
        "url": url,
        "title": title[:500],
        "summary_ru": (rec.get("summary_ru") or "")[:2000],
        "summary_en": (rec.get("summary_en") or "")[:2000],
        "published_at": rec.get("published_at"),
        "discovered_at": (
            rec.get("discovered_at")
            or datetime.now(timezone.utc).isoformat()
        ),
        "tags_json": json.dumps(tags, ensure_ascii=False),
        "novelty_score": novelty,
        "relevance_hint": relevance,
        "raw_payload": json.dumps(rec, ensure_ascii=False)[:8000],
    }


async def merge_inbox(
    db, inbox_dir: str | Path = DEFAULT_INBOX_DIR,
    archive_dir: str | Path | None = DEFAULT_ARCHIVE_DIR,
) -> dict[str, int]:
    """Прочитать *.json из inbox, замёржить в БД, при успехе — перенести в archive.

    Каждый файл — JSON-массив объектов (формат сканера Wave R2). Сломанный файл
    оставляем на месте, помечая в результате; рабочие — мерджим и перемещаем.
    """
    inbox = Path(inbox_dir)
    archive = Path(archive_dir) if archive_dir else None
    if not inbox.exists():
        return {"files": 0, "records": 0, "inserted": 0, "broken": 0}
    files = sorted(inbox.glob("*.json"))
    records_seen = 0
    inserted_total = 0
    broken = 0
    if archive:
        archive.mkdir(parents=True, exist_ok=True)
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            broken += 1
            continue
        if not isinstance(payload, list):
            broken += 1
            continue
        clean: list[dict] = []
        for rec in payload:
            norm = _normalize_finding(rec)
            if norm is not None:
                clean.append(norm)
        records_seen += len(payload)
        if clean:
            inserted_total += await db.insert_radar_findings(clean)
        if archive:
            shutil.move(str(path), str(archive / path.name))
    return {
        "files": len(files), "records": records_seen,
        "inserted": inserted_total, "broken": broken,
    }


# ── Apply (R1: только note-стаб; idea/topic/tech_debt — R3) ─────────────

SUPPORTED_APPLY_KINDS_R1 = ("note",)
SUPPORTED_APPLY_KINDS_R3 = ("idea", "topic", "tech_debt")


_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_filename(s: str, fallback: str = "finding") -> str:
    cleaned = _SAFE_NAME.sub("-", s.strip()).strip("-")
    return cleaned[:60] or fallback


async def apply_as_note(
    db, finding_id: int, project_slug: str,
    applied_dir: str | Path = DEFAULT_APPLIED_DIR,
) -> str:
    """Сохранить finding как markdown-стаб под `applied/{slug}/`, пометить applied.

    Возвращает путь созданного файла (он же — applied_to_ref). Идемпотентно:
    если файл с тем же именем уже существует — добавляет суффикс с timestamp-ом.
    """
    finding = await db.get_radar_finding(finding_id)
    if finding is None:
        raise ValueError(f"finding {finding_id} not found")
    target_dir = Path(applied_dir) / project_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    date_part = (finding.get("published_at") or finding["discovered_at"])[:10]
    base = f"{date_part}-{_safe_filename(finding['title'], fallback=str(finding_id))}"
    candidate = target_dir / f"{base}.md"
    if candidate.exists():
        suffix = datetime.now(timezone.utc).strftime("%H%M%S")
        candidate = target_dir / f"{base}-{suffix}.md"
    try:
        tags = json.loads(finding.get("tags_json") or "[]")
    except json.JSONDecodeError:
        tags = []
    front = [
        "---",
        f"source: {finding['source_key']}",
        f"url: {finding['url']}",
        f"discovered_at: {finding['discovered_at']}",
        f"published_at: {finding.get('published_at') or ''}",
        f"tags: [{', '.join(tags)}]",
        f"novelty: {finding.get('novelty_score') if finding.get('novelty_score') is not None else ''}",
        "---",
        "",
        f"# {finding['title']}",
        "",
        finding.get("summary_ru") or finding.get("summary_en") or "",
        "",
        f"Источник: <{finding['url']}>",
    ]
    candidate.write_text("\n".join(front), encoding="utf-8")
    ref = str(candidate)
    await db.mark_radar_finding_applied(finding_id, "note", ref)
    return ref
