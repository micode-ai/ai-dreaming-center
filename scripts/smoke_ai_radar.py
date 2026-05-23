"""Smoke-тест AI Radar — Wave R1.

Покрывает (в одном проходе, на временной БД и каталогах):
  - load_sources: парсит YAML с people/orgs/feeds, типы кинда расставлены.
  - insert_radar_findings: повторная вставка по тому же (source_key, url)
    не плодит дубли — UNIQUE-индекс.
  - merge_inbox: валидный JSON мерджится, файл перемещается в archive;
    сломанный JSON остаётся в inbox + считается broken.
  - list_radar_findings: фильтры status/source_key/since_days работают.
  - apply_as_note: пишет markdown с frontmatterʼом, статус → 'applied',
    applied_to_kind = 'note', applied_to_ref указывает на реальный файл.
  - pin_radar_finding_to_project: добавляет slug, повтор не дублирует.

Выход 0 — всё ок; ненулевой код + диагностика в stderr — что упало.
"""
from __future__ import annotations
import asyncio
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dreaming.services.db import SqliteDB  # noqa: E402
from dreaming.services import ai_radar  # noqa: E402


_YAML = """\
people:
  - key: karpathy
    name: "Andrej Karpathy"
    x: "https://x.com/karpathy"
    tags: [agents, llm]
orgs:
  - key: anthropic
    name: "Anthropic"
    news: "https://www.anthropic.com/news"
    tags: [safety]
feeds:
  - key: hf_daily
    name: "HF Daily"
    url: "https://huggingface.co/papers"
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rec(source_key: str, url: str, **over) -> dict:
    base = {
        "source_key": source_key, "source_kind": "feed",
        "url": url, "title": f"Title {url}",
        "summary_ru": "Сводка RU", "summary_en": "Summary EN",
        "tags": ["ai", "trend"],
        "discovered_at": _now_iso(),
    }
    base.update(over)
    return base


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


async def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="dc_smoke_radar_"))
    db_path = tmp / "test.db"
    inbox = tmp / "inbox"
    archive = tmp / "archive"
    applied = tmp / "applied"
    inbox.mkdir(parents=True)

    # ── load_sources ───────────────────────────────────────────────
    sources_yaml = tmp / "sources.yaml"
    sources_yaml.write_text(_YAML, encoding="utf-8")
    wl = ai_radar.load_sources(sources_yaml)
    if len(wl.sources) != 3:
        fail(f"watchlist: expected 3 sources, got {len(wl.sources)}")
        return 1
    by_kind = {s.key: s.kind for s in wl.sources}
    expected_kinds = {"karpathy": "person", "anthropic": "org", "hf_daily": "feed"}
    if by_kind != expected_kinds:
        fail(f"watchlist kinds wrong: {by_kind} vs {expected_kinds}")
        return 1
    print("ok: load_sources — 3 entries, kinds correct")

    db = SqliteDB(str(db_path))
    await db.connect()
    try:
        # ── insert_radar_findings (uniq dedup) ─────────────────────
        recs = [
            ai_radar._normalize_finding(_rec("karpathy", "https://example.test/k1")),
            ai_radar._normalize_finding(_rec("anthropic", "https://example.test/a1")),
        ]
        n1 = await db.insert_radar_findings(recs)
        n2 = await db.insert_radar_findings(recs)  # дубликаты
        if n1 != 2 or n2 != 0:
            fail(f"insert dedup: first={n1} (want 2), second={n2} (want 0)")
            return 1
        print(f"ok: insert_radar_findings — first 2, repeat 0 (UNIQUE works)")

        # ── merge_inbox: один валидный + один битый ────────────────
        good = [
            _rec("hf_daily", "https://example.test/h1"),
            _rec("hf_daily", "https://example.test/h2"),
        ]
        (inbox / "2026-05-23-batch-0-hf_daily.json").write_text(
            json.dumps(good, ensure_ascii=False), encoding="utf-8",
        )
        (inbox / "broken.json").write_text("{ this is not json", encoding="utf-8")
        result = await ai_radar.merge_inbox(db, inbox_dir=inbox, archive_dir=archive)
        if result["inserted"] != 2 or result["broken"] != 1:
            fail(f"merge_inbox: inserted={result['inserted']} (want 2), "
                 f"broken={result['broken']} (want 1)")
            return 1
        if not (archive / "2026-05-23-batch-0-hf_daily.json").exists():
            fail("merge_inbox: good file not archived")
            return 1
        if not (inbox / "broken.json").exists():
            fail("merge_inbox: broken file should remain in inbox")
            return 1
        print("ok: merge_inbox — 2 inserted, 1 broken left in inbox, good file archived")

        # ── list_radar_findings: фильтры ───────────────────────────
        all_rows = await db.list_radar_findings()
        if len(all_rows) != 4:
            fail(f"list all: expected 4, got {len(all_rows)}")
            return 1
        by_src = await db.list_radar_findings(source_key="anthropic")
        if len(by_src) != 1:
            fail(f"list by source: expected 1, got {len(by_src)}")
            return 1
        recent = await db.list_radar_findings(since_days=1)
        if len(recent) != 4:
            fail(f"list since_days=1: expected 4, got {len(recent)}")
            return 1
        print("ok: list_radar_findings — total/source/since_days filters")

        # ── pin_radar_finding_to_project + project filter ──────────
        target_id = by_src[0]["id"]
        await db.pin_radar_finding_to_project(target_id, "demo-project")
        # Повторный pin — не должен дублировать.
        await db.pin_radar_finding_to_project(target_id, "demo-project")
        row = await db.get_radar_finding(target_id)
        pinned = [s for s in (row["pinned_projects"] or "").split(",") if s]
        if pinned != ["demo-project"]:
            fail(f"pin: pinned_projects = {pinned} (want ['demo-project'])")
            return 1
        proj_rows = await db.list_radar_findings(project_slug="demo-project")
        if len(proj_rows) != 1 or proj_rows[0]["id"] != target_id:
            fail(f"project filter: expected 1 with id={target_id}, got {len(proj_rows)}")
            return 1
        print("ok: pin + project filter")

        # ── apply_as_note ──────────────────────────────────────────
        note_target = all_rows[0]["id"]
        path_str = await ai_radar.apply_as_note(
            db, note_target, "demo-project", applied_dir=applied,
        )
        note_path = Path(path_str)
        if not note_path.exists() or not note_path.suffix == ".md":
            fail(f"apply_as_note: file not created at {path_str}")
            return 1
        body = note_path.read_text(encoding="utf-8")
        if "---" not in body or "url:" not in body:
            fail("apply_as_note: frontmatter missing")
            return 1
        refreshed = await db.get_radar_finding(note_target)
        if refreshed["status"] != "applied" or refreshed["applied_to_kind"] != "note":
            fail(f"apply_as_note: status={refreshed['status']}, "
                 f"kind={refreshed['applied_to_kind']}")
            return 1
        if refreshed["applied_to_ref"] != path_str:
            fail(f"apply_as_note: ref mismatch {refreshed['applied_to_ref']} vs {path_str}")
            return 1
        print(f"ok: apply_as_note — {note_path.name}")

        # ── set_radar_finding_status ───────────────────────────────
        other_id = [r["id"] for r in all_rows if r["id"] != note_target][0]
        if not await db.set_radar_finding_status(other_id, "dismissed"):
            fail("set_status returned False")
            return 1
        dismissed = await db.list_radar_findings(status="dismissed")
        if len(dismissed) != 1 or dismissed[0]["id"] != other_id:
            fail("dismissed filter returned wrong rows")
            return 1
        print("ok: set_status + status filter")

        print("PASS")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
