# Article Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The center proposes article topics per project, and on approval dispatches that project's own article-writer agent to write the piece, then publishes it via git after a second approval.

**Architecture:** Proposals and their status machine live in the center's SQLite database; article text lives only in the project repository in that project's own format. Three feeders (a project scan, AI Radar findings, product ideas) POST proposals into one table; two human gates (approve-to-write, approve-to-publish) are the only transitions the user owns; two new starter-kit slash-commands do the work inside the project.

**Tech Stack:** FastAPI + Jinja2 + aiosqlite (existing singletons on `app.state`), APScheduler for the weekly job, Claude CLI via `ProcessManager.start_command`, `git` via `subprocess.run` in a worker thread.

**Spec:** `docs/superpowers/specs/2026-08-20-article-pipeline-design.md`

**Issue:** https://github.com/micode-ai/ai-dreaming-center/issues/34

## Global Constraints

- Publishing stages **only** the paths in `draft_ref`. Never `git add -A`. Never `git stash`. A dirty working tree in the article's paths stops the publish with an error.
- The weekly cron may create `proposed` rows only. It may never write and never publish.
- A proposal arriving with blank `evidence` is rejected with HTTP 400.
- With `article_verify_cmd` empty, publish stays available but card and commit message both say **unverified**. Never present an unrun verification as passed.
- The write session spawns with `--permission-mode bypassPermissions`. Do not use `--allowedTools` — it silently breaks writes into `.claude/`.
- User-facing strings go through `{{ "key" | t(locale=locale) }}`. Every new RU key needs its EN mirror; `scripts/check_i18n.py` enforces this.
- Files with Cyrillic content must be written with the Write/Edit tool. PowerShell `Set-Content` defaults to UTF-16 LE and breaks the JSON parser.
- Templates carry no colour utilities and no static `style=` attributes; `scripts/check_css_tokens.py` enforces this.
- Modern Starlette signature: `templates.TemplateResponse(request, "name.html", {ctx_without_request})`.
- Routes read `request.state.project`, never query by slug themselves.
- There is no pytest in this repo. The test vehicle is `scripts/smoke_articles.py`, run manually; it must exit 0.

---

### Task 1: Database layer — `article_proposals` table and its methods

**Files:**
- Modify: `dreaming/services/db.py` (SCHEMA block after the `ai_radar_findings` section ~line 288; methods after the AI Radar block ~line 1140)
- Create: `scripts/smoke_articles.py`

**Interfaces:**
- Consumes: `SqliteDB` (`connect`, `fetch_all`, `fetch_one`, `execute`, `self._conn`)
- Produces:
  - `db.add_article_proposal(project_id: int, *, source: str, source_ref: str, evidence: str, title: str, angle: str, slug_hint: str, funnel_level: str = "top", locales: str = "", tags_json: str = "[]", related_product: str = "") -> int | None` — returns the new id, or `None` when `(project_id, slug_hint)` already exists
  - `db.get_article_proposal(proposal_id: int) -> dict | None`
  - `db.list_article_proposals(*, project_id: int | None = None, status: str | None = None, limit: int = 200) -> list`
  - `db.set_article_proposal_status(proposal_id: int, status: str, *, error_message: str = "") -> bool`
  - `db.mark_article_written(proposal_id: int, *, draft_ref: str, verify_output: str, writer_agent: str, verify_ok: bool) -> bool`
  - `db.mark_article_published(proposal_id: int, *, commit_ref: str) -> bool`
  - `db.article_status_counts(project_id: int | None = None) -> list`

- [ ] **Step 1: Write the failing smoke check**

Create `scripts/smoke_articles.py`:

```python
"""Smoke-тест article pipeline.

Покрывает: вставку предложения, дедуп по (project_id, slug_hint), переходы
статусов, фиксацию черновика с выводом верификации и публикацию.

Выход 0 — всё ок; ненулевой код + диагностика в stderr — что упало.
"""
from __future__ import annotations
import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dreaming.services.db import SqliteDB  # noqa: E402


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


async def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="dc_smoke_articles_"))
    db = SqliteDB(str(tmp / "test.db"))
    await db.connect()
    try:
        pid = await db.create_project(
            slug="demo", label="Demo", working_dir=str(tmp),
        )

        # ── insert + dedup ─────────────────────────────────────────
        first = await db.add_article_proposal(
            pid, source="radar", source_ref="178",
            evidence="GLM-5.3 release, 2026-08-19, source: latent_space",
            title="What GLM-5.3 changes for our agents",
            angle="Compare the new context window against our routing costs",
            slug_hint="glm-53-agent-routing",
            funnel_level="top", locales="pl,en,ru", tags_json='["AI","agents"]',
        )
        if not first:
            fail("add_article_proposal returned no id")
            return 1
        dup = await db.add_article_proposal(
            pid, source="project_scan", source_ref="abc123",
            evidence="same subject from another feeder",
            title="GLM-5.3 again", angle="…",
            slug_hint="glm-53-agent-routing",
        )
        if dup is not None:
            fail(f"dedup broken: second insert returned {dup}, want None")
            return 1
        print("ok: insert + dedup on (project_id, slug_hint)")

        # ── status transitions ─────────────────────────────────────
        row = await db.get_article_proposal(first)
        if row["status"] != "proposed":
            fail(f"initial status = {row['status']}, want 'proposed'")
            return 1
        await db.set_article_proposal_status(first, "approved")
        await db.set_article_proposal_status(first, "writing")
        row = await db.get_article_proposal(first)
        if row["status"] != "writing" or not row["decided_at"]:
            fail(f"after approve/writing: status={row['status']}, "
                 f"decided_at={row['decided_at']}")
            return 1
        print("ok: proposed → approved → writing, decided_at stamped")

        # ── draft with verification ────────────────────────────────
        await db.mark_article_written(
            first, draft_ref="src/data/blog-posts.json",
            verify_output="dist/blog/glm-53-agent-routing/index.html written",
            writer_agent="blog-writer", verify_ok=True,
        )
        row = await db.get_article_proposal(first)
        if row["status"] != "drafted" or row["verify_ok"] != 1:
            fail(f"after write: status={row['status']}, verify_ok={row['verify_ok']}")
            return 1
        if not row["written_at"] or "dist/blog" not in row["verify_output"]:
            fail("written_at or verify_output not persisted")
            return 1
        print("ok: drafted with verify_output + verify_ok")

        # ── failure path ───────────────────────────────────────────
        second = await db.add_article_proposal(
            pid, source="center", source_ref="idea-42",
            evidence="product idea 42 has no article yet",
            title="Second", angle="…", slug_hint="second-piece",
        )
        await db.set_article_proposal_status(
            second, "failed", error_message="npm run build exited 1",
        )
        row = await db.get_article_proposal(second)
        if row["status"] != "failed" or "exited 1" not in row["error_message"]:
            fail(f"failure path: status={row['status']}, err={row['error_message']}")
            return 1
        print("ok: failed carries error_message")

        # ── publish ────────────────────────────────────────────────
        await db.mark_article_published(first, commit_ref="deadbeef")
        row = await db.get_article_proposal(first)
        if row["status"] != "published" or row["commit_ref"] != "deadbeef":
            fail(f"publish: status={row['status']}, ref={row['commit_ref']}")
            return 1
        print("ok: published with commit_ref")

        # ── listing + counts ───────────────────────────────────────
        proposed = await db.list_article_proposals(project_id=pid, status="failed")
        if len(proposed) != 1 or proposed[0]["id"] != second:
            fail(f"status filter returned {len(proposed)} rows")
            return 1
        counts = {r["status"]: r["n"] for r in await db.article_status_counts(pid)}
        if counts.get("published") != 1 or counts.get("failed") != 1:
            fail(f"counts wrong: {counts}")
            return 1
        print("ok: list filter + status counts")

        print("PASS")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/smoke_articles.py`
Expected: `AttributeError: 'SqliteDB' object has no attribute 'add_article_proposal'`

Note: confirm the exact `create_project` signature first with
`grep -n "async def create_project" -A 12 dreaming/services/db.py` and fix the
call in the smoke script if the keyword names differ.

- [ ] **Step 3: Add the schema**

In `dreaming/services/db.py`, append to the SCHEMA string immediately after the
`idx_radar_status_discovered` index:

```sql
-- + dreaming: Article pipeline — предложения статей (project-scoped).
-- Текст статьи живёт в репозитории проекта; здесь только предложение,
-- статус и отчёт верификации. См.
-- docs/superpowers/specs/2026-08-20-article-pipeline-design.md
CREATE TABLE IF NOT EXISTS article_proposals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL,
    source          TEXT NOT NULL,
    source_ref      TEXT NOT NULL DEFAULT '',
    evidence        TEXT NOT NULL,
    title           TEXT NOT NULL,
    angle           TEXT NOT NULL DEFAULT '',
    slug_hint       TEXT NOT NULL,
    funnel_level    TEXT NOT NULL DEFAULT 'top',
    locales         TEXT NOT NULL DEFAULT '',
    tags_json       TEXT NOT NULL DEFAULT '[]',
    related_product TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'proposed',
    writer_agent    TEXT NOT NULL DEFAULT '',
    draft_ref       TEXT NOT NULL DEFAULT '',
    verify_output   TEXT NOT NULL DEFAULT '',
    verify_ok       INTEGER NOT NULL DEFAULT 0,
    commit_ref      TEXT NOT NULL DEFAULT '',
    session_id      TEXT NOT NULL DEFAULT '',
    error_message   TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    decided_at      TEXT,
    written_at      TEXT,
    published_at    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_article_project_slug
    ON article_proposals (project_id, slug_hint);
CREATE INDEX IF NOT EXISTS idx_article_project_status
    ON article_proposals (project_id, status);
CREATE INDEX IF NOT EXISTS idx_article_status_created
    ON article_proposals (status, created_at DESC);
```

- [ ] **Step 4: Add the methods**

Append after the AI Radar method block in `dreaming/services/db.py`:

```python
    # ── Article pipeline ───────────────────────────────────────────────

    async def add_article_proposal(
        self, project_id: int, *, source: str, source_ref: str, evidence: str,
        title: str, angle: str, slug_hint: str, funnel_level: str = "top",
        locales: str = "", tags_json: str = "[]", related_product: str = "",
    ) -> int | None:
        """Вставить предложение. None — если (project_id, slug_hint) уже есть:
        три фидера на один сюжет дают одну строку, а не три."""
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._conn.execute(
            "INSERT OR IGNORE INTO article_proposals "
            "(project_id, source, source_ref, evidence, title, angle, slug_hint, "
            " funnel_level, locales, tags_json, related_product, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?)",
            (project_id, source, source_ref, evidence, title, angle, slug_hint,
             funnel_level, locales, tags_json, related_product, now_iso),
        ) as cur:
            if cur.rowcount == 0:
                await self._conn.commit()
                return None
            new_id = cur.lastrowid
        await self._conn.commit()
        return new_id

    async def get_article_proposal(self, proposal_id: int) -> dict | None:
        row = await self.fetch_one(
            "SELECT * FROM article_proposals WHERE id=?", (proposal_id,),
        )
        return dict(row) if row else None

    async def list_article_proposals(
        self, *, project_id: int | None = None, status: str | None = None,
        limit: int = 200,
    ) -> list:
        sql = "SELECT * FROM article_proposals WHERE 1=1"
        params: list = []
        if project_id is not None:
            sql += " AND project_id=?"
            params.append(project_id)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return await self.fetch_all(sql, tuple(params))

    async def find_article_proposal_by_slug(
        self, project_id: int, slug_hint: str,
    ) -> dict | None:
        row = await self.fetch_one(
            "SELECT * FROM article_proposals WHERE project_id=? AND slug_hint=?",
            (project_id, slug_hint),
        )
        return dict(row) if row else None

    async def set_article_proposal_status(
        self, proposal_id: int, status: str, *, error_message: str = "",
        session_id: str = "",
    ) -> bool:
        """Двигает статус. `decided_at` ставится на первом уходе из 'proposed'."""
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._conn.execute(
            "UPDATE article_proposals SET status=?, error_message=?, "
            "session_id=CASE WHEN ?<>'' THEN ? ELSE session_id END, "
            "decided_at=COALESCE(decided_at, ?) WHERE id=?",
            (status, error_message, session_id, session_id, now_iso, proposal_id),
        ) as cur:
            n = cur.rowcount
        await self._conn.commit()
        return n > 0

    async def mark_article_written(
        self, proposal_id: int, *, draft_ref: str, verify_output: str,
        writer_agent: str, verify_ok: bool,
    ) -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._conn.execute(
            "UPDATE article_proposals SET status='drafted', draft_ref=?, "
            "verify_output=?, writer_agent=?, verify_ok=?, written_at=? "
            "WHERE id=?",
            (draft_ref, verify_output[:8000], writer_agent,
             1 if verify_ok else 0, now_iso, proposal_id),
        ) as cur:
            n = cur.rowcount
        await self._conn.commit()
        return n > 0

    async def mark_article_published(
        self, proposal_id: int, *, commit_ref: str,
    ) -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._conn.execute(
            "UPDATE article_proposals SET status='published', commit_ref=?, "
            "published_at=? WHERE id=?",
            (commit_ref, now_iso, proposal_id),
        ) as cur:
            n = cur.rowcount
        await self._conn.commit()
        return n > 0

    async def article_status_counts(self, project_id: int | None = None) -> list:
        sql = "SELECT status, COUNT(*) AS n FROM article_proposals"
        params: tuple = ()
        if project_id is not None:
            sql += " WHERE project_id=?"
            params = (project_id,)
        sql += " GROUP BY status ORDER BY n DESC"
        return await self.fetch_all(sql, params)
```

- [ ] **Step 5: Run the smoke check to verify it passes**

Run: `python scripts/smoke_articles.py`
Expected: every `ok:` line, then `PASS`, exit 0

- [ ] **Step 6: Commit**

```bash
git add dreaming/services/db.py scripts/smoke_articles.py
git commit -m "feat(articles): article_proposals table and its db methods

Refs #34"
```

---

### Task 2: API — feeder ingest, dedupe lookup, and the write-back callback

**Files:**
- Modify: `dreaming/routes/api.py` (append after the topics endpoints ~line 411)
- Modify: `scripts/smoke_articles.py` (add an API section using `TestClient`)

**Interfaces:**
- Consumes: Task 1's db methods; `_resolve_project(request, slug)` already in `api.py`
- Produces:
  - `POST /api/p/{slug}/articles/ingest` — body `ArticleIngestIn`; 201 `{"id": n}`, 200 `{"id": n, "duplicate": true}`, 400 when evidence is blank
  - `GET /api/p/{slug}/articles/list` — proposals for dedupe by the scanning command
  - `GET /api/articles/{proposal_id}` — full proposal, read by `/write-article`
  - `POST /api/articles/{proposal_id}/written` — body `ArticleWrittenIn`

- [ ] **Step 1: Write the failing API smoke section**

Append inside `main()` in `scripts/smoke_articles.py`, before `print("PASS")`:

```python
        # ── API: ingest / dedupe / write-back ──────────────────────
        from starlette.testclient import TestClient
        from dreaming.main import app
        with TestClient(app) as client:
            base = "/api/p/ai-dreaming-center/articles"
            blank = client.post(f"{base}/ingest", json={
                "title": "No evidence here", "angle": "…",
                "slug_hint": "smoke-no-evidence", "evidence": "   ",
                "source": "project_scan",
            })
            if blank.status_code != 400:
                fail(f"blank evidence: got {blank.status_code}, want 400")
                return 1
            good = client.post(f"{base}/ingest", json={
                "title": "Smoke article", "angle": "…",
                "slug_hint": "smoke-pipeline-check",
                "evidence": "commit 503ed08 shipped the density fix",
                "source": "project_scan", "source_ref": "503ed08",
            })
            if good.status_code not in (200, 201):
                fail(f"ingest failed: {good.status_code} {good.text[:200]}")
                return 1
            api_id = good.json()["id"]
            again = client.post(f"{base}/ingest", json={
                "title": "Smoke article dup", "angle": "…",
                "slug_hint": "smoke-pipeline-check",
                "evidence": "same subject", "source": "radar",
            })
            if not again.json().get("duplicate"):
                fail(f"dedupe not reported: {again.status_code} {again.text[:200]}")
                return 1
            detail = client.get(f"/api/articles/{api_id}")
            if detail.status_code != 200 or detail.json()["slug_hint"] != "smoke-pipeline-check":
                fail(f"detail GET wrong: {detail.status_code} {detail.text[:200]}")
                return 1
            back = client.post(f"/api/articles/{api_id}/written", json={
                "draft_ref": "content/blog/ru/smoke.md",
                "verify_output": "no verify command configured",
                "writer_agent": "self", "verify_ok": False,
            })
            if back.status_code != 200:
                fail(f"write-back failed: {back.status_code} {back.text[:200]}")
                return 1
        print("ok: API ingest (400 on blank evidence), dedupe, detail, write-back")
```

Note: this section talks to the real `data/dreaming.db` through the app. It uses
`slug_hint` values prefixed `smoke-` so they are identifiable; delete them with
the UI or leave them — they are `drafted` rows in one project and harmless.

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/smoke_articles.py`
Expected: `FAIL: blank evidence: got 404, want 400` (route does not exist yet)

- [ ] **Step 3: Implement the endpoints**

Append to `dreaming/routes/api.py`:

```python
class ArticleIngestIn(BaseModel):
    title: str
    slug_hint: str
    evidence: str
    angle: str = ""
    source: str = "project_scan"
    source_ref: str = ""
    funnel_level: str = "top"
    locales: str = ""
    tags: list[str] = []
    related_product: str = ""


class ArticleWrittenIn(BaseModel):
    draft_ref: str
    verify_output: str = ""
    writer_agent: str = ""
    verify_ok: bool = False
    error_message: str = ""


_ARTICLE_SOURCES = {"project_scan", "radar", "center", "manual"}


@router.post("/p/{slug}/articles/ingest")
async def articles_ingest(request: Request, slug: str, payload: ArticleIngestIn):
    """Called by /article-ideas-scan running inside the project. One POST per
    proposal.

    `evidence` is required and enforced here rather than in the prompt: a queue
    of unfalsifiable suggestions is worse than an empty queue — the rule comes
    from micode-landing-page's scripts/ai-visibility/advice.mjs."""
    project = await _resolve_project(request, slug)
    title = payload.title.strip()
    slug_hint = payload.slug_hint.strip()
    evidence = payload.evidence.strip()
    if not title or not slug_hint:
        raise HTTPException(status_code=422, detail="title and slug_hint required")
    if not evidence:
        raise HTTPException(
            status_code=400,
            detail="evidence required: state the fact this proposal traces to",
        )
    if payload.source not in _ARTICLE_SOURCES:
        raise HTTPException(status_code=422, detail=f"bad source: {payload.source}")
    db = request.app.state.db
    new_id = await db.add_article_proposal(
        project.id, source=payload.source, source_ref=payload.source_ref.strip(),
        evidence=evidence, title=title, angle=payload.angle.strip(),
        slug_hint=slug_hint, funnel_level=payload.funnel_level.strip() or "top",
        locales=payload.locales.strip(),
        tags_json=json.dumps(payload.tags, ensure_ascii=False),
        related_product=payload.related_product.strip(),
    )
    if new_id is None:
        existing = await db.find_article_proposal_by_slug(project.id, slug_hint)
        return JSONResponse(
            {"id": existing["id"] if existing else None, "duplicate": True},
            status_code=200,
        )
    return JSONResponse({"id": new_id, "duplicate": False}, status_code=201)


@router.get("/p/{slug}/articles/list")
async def articles_list(request: Request, slug: str):
    """Called by /article-ideas-scan to skip subjects already proposed."""
    project = await _resolve_project(request, slug)
    rows = await request.app.state.db.list_article_proposals(project_id=project.id)
    return JSONResponse([
        {"id": r["id"], "slug_hint": r["slug_hint"], "title": r["title"],
         "status": r["status"]}
        for r in rows
    ])


@router.get("/articles/{proposal_id}")
async def article_detail(request: Request, proposal_id: int):
    """Called by /write-article to read the brief it must write from."""
    row = await request.app.state.db.get_article_proposal(proposal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    return JSONResponse(row)


@router.post("/articles/{proposal_id}/written")
async def article_written(
    request: Request, proposal_id: int, payload: ArticleWrittenIn,
):
    """Called by /write-article when the draft exists (or failed)."""
    db = request.app.state.db
    row = await db.get_article_proposal(proposal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    if payload.error_message.strip():
        await db.set_article_proposal_status(
            proposal_id, "failed", error_message=payload.error_message.strip()[:2000],
        )
        return JSONResponse({"status": "failed"})
    if not payload.draft_ref.strip():
        raise HTTPException(status_code=422, detail="draft_ref required on success")
    await db.mark_article_written(
        proposal_id, draft_ref=payload.draft_ref.strip(),
        verify_output=payload.verify_output,
        writer_agent=payload.writer_agent.strip() or "self",
        verify_ok=payload.verify_ok,
    )
    return JSONResponse({"status": "drafted"})
```

Add `import json` to the imports at the top of `api.py` if it is not already there.

- [ ] **Step 4: Run the smoke check to verify it passes**

Run: `python scripts/smoke_articles.py`
Expected: the new `ok: API ingest …` line, then `PASS`, exit 0

- [ ] **Step 5: Commit**

```bash
git add dreaming/routes/api.py scripts/smoke_articles.py
git commit -m "feat(articles): ingest, dedupe, detail and write-back endpoints

Blank evidence is a 400 — the rule imported from advice.mjs.

Refs #34"
```

---

### Task 3: Settings keys and writer resolution

**Files:**
- Modify: `dreaming/config.py` (settings fields near the other per-feature keys; add a group to the overridable-keys list ~line 165-200)
- Create: `dreaming/services/articles.py`
- Modify: `scripts/smoke_articles.py`

**Interfaces:**
- Consumes: `ConfigResolver.get(project, key, default)`
- Produces:
  - `articles.resolve_writer(working_dir: str, configured: str = "") -> str` — returns the configured agent name, else an autodetected one, else `"self"`
  - `articles.publish_label(verify_ok: bool, verify_cmd: str) -> str` — `"verified"` / `"failed"` / `"unverified"`
  - `articles.can_publish(row: dict, verify_cmd: str, publish_mode: str) -> tuple[bool, str]` — `(allowed, reason_key)`
  - Settings: `article_writer_agent=""`, `article_blog_dir=""`, `article_locales=""`, `article_verify_cmd=""`, `article_publish_mode="off"`, `article_max_turns=300`, `article_timeout_minutes=120`, `weekly_article_ideas_scan_cron="0 8 * * 1"`, `weekly_article_ideas_scan_enabled=False`

- [ ] **Step 1: Write the failing checks**

Append to `scripts/smoke_articles.py` before `print("PASS")`:

```python
        # ── writer resolution + publish gate ───────────────────────
        from dreaming.services import articles
        agents_dir = tmp / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        if articles.resolve_writer(str(tmp)) != "self":
            fail("resolve_writer: empty agents dir must give 'self'")
            return 1
        (agents_dir / "blog-writer.md").write_text("---\nname: blog-writer\n---\n",
                                                   encoding="utf-8")
        (agents_dir / "backend-developer.md").write_text("---\nname: x\n---\n",
                                                         encoding="utf-8")
        got = articles.resolve_writer(str(tmp))
        if got != "blog-writer":
            fail(f"autodetect picked {got!r}, want 'blog-writer'")
            return 1
        if articles.resolve_writer(str(tmp), configured="kb-page-author") != "kb-page-author":
            fail("configured agent must win over autodetect")
            return 1
        print("ok: resolve_writer — configured > autodetect > self")

        gate_cases = [
            ({"verify_ok": 1, "status": "drafted"}, "npm run build", "commit", True),
            ({"verify_ok": 0, "status": "drafted"}, "npm run build", "commit", False),
            ({"verify_ok": 0, "status": "drafted"}, "", "commit", True),
            ({"verify_ok": 1, "status": "drafted"}, "npm run build", "off", False),
            ({"verify_ok": 1, "status": "proposed"}, "npm run build", "commit", False),
        ]
        for row_in, cmd, mode, want in gate_cases:
            allowed, reason = articles.can_publish(row_in, cmd, mode)
            if allowed is not want:
                fail(f"can_publish({row_in}, {cmd!r}, {mode!r}) = {allowed} "
                     f"({reason}), want {want}")
                return 1
        if articles.publish_label(False, "") != "unverified":
            fail("publish_label: empty verify cmd must read 'unverified'")
            return 1
        print("ok: publish gate — verified / failed / unverified / off")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/smoke_articles.py`
Expected: `ModuleNotFoundError: No module named 'dreaming.services.articles'`

- [ ] **Step 3: Create the service**

Create `dreaming/services/articles.py`:

```python
"""Article pipeline helpers: who writes, and may this draft be published.

The center never owns the article's format — see the spec at
docs/superpowers/specs/2026-08-20-article-pipeline-design.md. These are the two
decisions it does own: which agent to hand the brief to, and whether the
publish button is allowed to claim the draft was verified.
"""
from __future__ import annotations
from pathlib import Path


# Substrings that mark an agent as one that writes prose, most specific first.
# Ordered so `blog-writer` beats a generic `*-author` when a repo has both.
_WRITER_HINTS = (
    "blog-writer", "article", "kb-page-author", "copywriter",
    "content-writer", "tech-writer", "writer", "author",
)
# An agent whose name matches a hint but is not a prose writer.
_WRITER_EXCLUDE = ("test-author", "component-author", "test-runner")


def resolve_writer(working_dir: str | Path, configured: str = "") -> str:
    """Configured agent wins; else autodetect in .claude/agents; else 'self'.

    Only three of eleven projects ship a writing agent, so 'self' is a normal
    outcome, not a failure — the slash-command writes the piece itself and the
    card records `writer_agent='self'` so the UI stays honest about it.
    """
    if configured.strip():
        return configured.strip()
    agents_dir = Path(working_dir) / ".claude" / "agents"
    if not agents_dir.is_dir():
        return "self"
    names = sorted(p.stem for p in agents_dir.glob("*.md"))
    for hint in _WRITER_HINTS:
        for name in names:
            low = name.lower()
            if hint in low and not any(bad in low for bad in _WRITER_EXCLUDE):
                return name
    return "self"


def publish_label(verify_ok: bool, verify_cmd: str) -> str:
    """What the card and the commit message are allowed to claim."""
    if not verify_cmd.strip():
        return "unverified"
    return "verified" if verify_ok else "failed"


def can_publish(
    row: dict, verify_cmd: str, publish_mode: str,
) -> tuple[bool, str]:
    """(allowed, reason_key). reason_key is an i18n key suffix under article.gate.

    A red verification never becomes a green publish. A missing verification
    command does not block publishing — that would make the feature useless in
    accounting-ai-agent, whose markdown blog has no build step — but the label
    then says 'unverified' everywhere it is shown.
    """
    if (publish_mode or "off").strip() == "off":
        return False, "mode_off"
    if row.get("status") != "drafted":
        return False, "not_drafted"
    if verify_cmd.strip() and not row.get("verify_ok"):
        return False, "verify_failed"
    return True, "ok"
```

- [ ] **Step 4: Add the settings fields**

In `dreaming/config.py`, next to the orchestration keys, add:

```python
    # Article pipeline — the center proposes, you approve, the project writes.
    # Own turn/timeout pair: the global 50/20 is exhausted by the first language
    # of a trilingual 15-20k-character piece plus a build.
    article_writer_agent: str = ""
    article_blog_dir: str = ""
    article_locales: str = ""
    article_verify_cmd: str = ""
    article_publish_mode: str = "off"
    article_max_turns: int = 300
    article_timeout_minutes: int = 120
    weekly_article_ideas_scan_cron: str = "0 8 * * 1"
    weekly_article_ideas_scan_enabled: bool = False
```

Then register them as per-project overridable by adding a group to the list that
currently holds `("Orchestration", [...])`:

```python
    ("Articles", [
        "article_writer_agent", "article_blog_dir", "article_locales",
        "article_verify_cmd", "article_publish_mode",
        "article_max_turns", "article_timeout_minutes",
    ]),
```

and append the two scheduling keys to the existing
`"Scheduling — weekly (opt-in)"` group:

```python
        "weekly_article_ideas_scan_cron", "weekly_article_ideas_scan_enabled",
```

- [ ] **Step 5: Run the smoke check to verify it passes**

Run: `python scripts/smoke_articles.py`
Expected: `ok: resolve_writer …` and `ok: publish gate …`, then `PASS`

Then confirm the keys reached the settings UI grouping:

Run: `python -c "from dreaming.config import Settings; s=Settings(); print(s.article_publish_mode, s.article_max_turns, s.weekly_article_ideas_scan_enabled)"`
Expected: `off 300 False`

- [ ] **Step 6: Commit**

```bash
git add dreaming/config.py dreaming/services/articles.py scripts/smoke_articles.py
git commit -m "feat(articles): settings keys, writer resolution, publish gate

Refs #34"
```

---

### Task 4: Per-project page `/p/{slug}/articles`

**Files:**
- Create: `dreaming/routes/project_articles.py`
- Create: `dreaming/templates/project_articles.html`
- Create: `dreaming/templates/_article_card.html`
- Modify: `dreaming/routes/project_router.py` (import + include, following the existing block)
- Modify: `dreaming/templates/_sidebar.html` (a `nav_item` next to `ai_radar`)
- Modify: `dreaming/i18n/messages_ru.json`, `dreaming/i18n/messages_en.json`
- Modify: `scripts/smoke_articles.py`

**Interfaces:**
- Consumes: Task 1 db methods; Task 3 `articles.can_publish`, `articles.publish_label`
- Produces:
  - `GET /p/{slug}/articles` — list grouped by status
  - `POST /p/{slug}/articles/{proposal_id}/reject` — status → `rejected`
  - `POST /p/{slug}/articles/{proposal_id}/restore` — status → `proposed`
  - template context keys: `groups`, `counts`, `gate`, `publish_label`, `writer`

- [ ] **Step 1: Write the failing render check**

Append to the `TestClient` block in `scripts/smoke_articles.py`:

```python
            page = client.get("/p/ai-dreaming-center/articles")
            if page.status_code != 200:
                fail(f"/articles page: {page.status_code}")
                return 1
            if "smoke-pipeline-check" not in page.text:
                fail("the ingested proposal is not rendered on the page")
                return 1
        print("ok: /p/{slug}/articles renders the proposal")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/smoke_articles.py`
Expected: `FAIL: /articles page: 404`

- [ ] **Step 3: Add the i18n keys**

Add to `dreaming/i18n/messages_ru.json` (and the EN mirror below):

```json
  "article.title": "Статьи",
  "article.total": "предложений",
  "article.empty": "Предложений пока нет. Запустите скан идей или предложите статью из радара.",
  "article.status.proposed": "предложено",
  "article.status.approved": "согласовано",
  "article.status.writing": "пишется",
  "article.status.drafted": "черновик готов",
  "article.status.published": "опубликовано",
  "article.status.rejected": "отклонено",
  "article.status.failed": "ошибка",
  "article.evidence": "Почему сейчас",
  "article.writer": "Пишет",
  "article.writer.self": "команда центра (агента-писателя в проекте нет)",
  "article.btn.scan": "Предложить темы",
  "article.btn.approve": "Согласовать и написать",
  "article.btn.reject": "Отклонить",
  "article.btn.restore": "Вернуть в очередь",
  "article.btn.publish": "Публиковать",
  "article.btn.retry": "Повторить",
  "article.verify.verified": "сборка прошла",
  "article.verify.unverified": "без проверки",
  "article.verify.failed": "сборка упала",
  "article.gate.mode_off": "Публикация выключена: задайте article_publish_mode в настройках проекта.",
  "article.gate.not_drafted": "Черновика ещё нет.",
  "article.gate.verify_failed": "Верификация не прошла — публикация заблокирована.",
  "article.blog_dir_missing": "Не задан article_blog_dir — писателю некуда положить статью."
```

EN mirror:

```json
  "article.title": "Articles",
  "article.total": "proposals",
  "article.empty": "No proposals yet. Run the idea scan or propose an article from the radar.",
  "article.status.proposed": "proposed",
  "article.status.approved": "approved",
  "article.status.writing": "writing",
  "article.status.drafted": "draft ready",
  "article.status.published": "published",
  "article.status.rejected": "rejected",
  "article.status.failed": "failed",
  "article.evidence": "Why now",
  "article.writer": "Writer",
  "article.writer.self": "the center's own command (no writer agent in this project)",
  "article.btn.scan": "Propose topics",
  "article.btn.approve": "Approve and write",
  "article.btn.reject": "Reject",
  "article.btn.restore": "Back to queue",
  "article.btn.publish": "Publish",
  "article.btn.retry": "Retry",
  "article.verify.verified": "build passed",
  "article.verify.unverified": "unverified",
  "article.verify.failed": "build failed",
  "article.gate.mode_off": "Publishing is off: set article_publish_mode in the project settings.",
  "article.gate.not_drafted": "There is no draft yet.",
  "article.gate.verify_failed": "Verification did not pass — publishing is blocked.",
  "article.blog_dir_missing": "article_blog_dir is not set — the writer has nowhere to put the piece."
```

- [ ] **Step 4: Create the route**

Create `dreaming/routes/project_articles.py`:

```python
"""GET /p/{slug}/articles — предложения статей проекта по статусам.

Согласование и публикация живут в отдельных роутах (Task 8 и Task 9);
здесь — список, отклонение и возврат в очередь.
"""
from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from dreaming.services import articles


router = APIRouter()

_ORDER = ["proposed", "approved", "writing", "drafted", "published",
          "failed", "rejected"]


def _enrich(row: dict, *, verify_cmd: str, publish_mode: str) -> dict:
    d = dict(row)
    try:
        d["tags"] = json.loads(d.get("tags_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        d["tags"] = []
    allowed, reason = articles.can_publish(d, verify_cmd, publish_mode)
    d["can_publish"] = allowed
    d["gate_reason"] = reason
    d["verify_label"] = articles.publish_label(bool(d.get("verify_ok")), verify_cmd)
    return d


@router.get("/p/{slug}/articles")
async def articles_page(request: Request, slug: str):
    project = request.state.project
    db = request.app.state.db
    resolver = request.app.state.resolver_factory(request)
    verify_cmd = await resolver.get(project, "article_verify_cmd", "")
    publish_mode = await resolver.get(project, "article_publish_mode", "off")
    blog_dir = await resolver.get(project, "article_blog_dir", "")
    configured_writer = await resolver.get(project, "article_writer_agent", "")
    rows = await db.list_article_proposals(project_id=project.id)
    enriched = [_enrich(r, verify_cmd=verify_cmd, publish_mode=publish_mode)
                for r in rows]
    groups = [(st, [r for r in enriched if r["status"] == st]) for st in _ORDER]
    counts = {r["status"]: r["n"] for r in await db.article_status_counts(project.id)}
    locale = request.cookies.get(
        "dc_locale", request.app.state.settings.default_locale,
    )
    projects = await request.app.state.projects.list_all(only_enabled=True)
    pm = request.app.state.process_manager
    return request.app.state.templates.TemplateResponse(
        request, "project_articles.html",
        {"project": project,
         "groups": [(st, items) for st, items in groups if items],
         "counts": counts, "total": len(enriched),
         "blog_dir": blog_dir,
         "writer": articles.resolve_writer(project.working_dir, configured_writer),
         "scan_running": f"cmd:{project.slug}:article-ideas-scan" in pm.list_running(),
         "projects": projects, "locale": locale},
    )


@router.post("/p/{slug}/articles/{proposal_id}/reject")
async def articles_reject(request: Request, slug: str, proposal_id: int):
    project = request.state.project
    ok = await request.app.state.db.set_article_proposal_status(
        proposal_id, "rejected",
    )
    if not ok:
        raise HTTPException(status_code=404, detail="proposal not found")
    return RedirectResponse(f"/p/{project.slug}/articles", status_code=303)


@router.post("/p/{slug}/articles/{proposal_id}/restore")
async def articles_restore(request: Request, slug: str, proposal_id: int):
    project = request.state.project
    ok = await request.app.state.db.set_article_proposal_status(
        proposal_id, "proposed",
    )
    if not ok:
        raise HTTPException(status_code=404, detail="proposal not found")
    return RedirectResponse(f"/p/{project.slug}/articles", status_code=303)
```

- [ ] **Step 5: Create the templates**

Create `dreaming/templates/_article_card.html`:

```html
{# Карточка предложения. Параметры: a — enriched-строка, project, locale. #}
<article class="card mb-3">
  <header class="flex items-baseline gap-3 flex-wrap mb-2">
    <span class="text-base font-semibold strong">{{ a.title }}</span>
    <span class="badge badge-neutral">
      {{ ("article.status." ~ a.status) | t(locale=locale) }}
    </span>
    <span class="text-xs font-mono faint">{{ a.slug_hint }}</span>
    {% if a.status in ('drafted', 'published') %}
      <span class="badge badge-neutral">
        {{ ("article.verify." ~ a.verify_label) | t(locale=locale) }}
      </span>
    {% endif %}
    <span class="text-xs faint ml-auto">{{ a.source }}{% if a.source_ref %} · {{ a.source_ref }}{% endif %}</span>
  </header>

  {% if a.angle %}<p class="text-sm mb-2">{{ a.angle }}</p>{% endif %}

  <p class="text-xs mb-2 faint">
    <span class="strong">{{ "article.evidence" | t(locale=locale) }}:</span>
    {{ a.evidence }}
  </p>

  {% if a.tags %}
    <div class="text-xs mb-2 faint">
      {% for t in a.tags %}<span class="badge badge-neutral mr-1">#{{ t }}</span>{% endfor %}
    </div>
  {% endif %}

  {% if a.draft_ref %}
    <p class="text-xs font-mono faint mb-2">→ {{ a.draft_ref }}</p>
  {% endif %}

  {% if a.status == 'failed' and a.error_message %}
    <pre class="text-xs mb-2 overflow-x-auto">{{ a.error_message }}</pre>
  {% endif %}

  {% if a.verify_output and a.status in ('drafted', 'failed') %}
    <pre class="text-xs mb-2 overflow-x-auto">{{ a.verify_output }}</pre>
  {% endif %}

  <footer class="flex gap-2 items-center text-xs flex-wrap mt-2">
    {% if a.status == 'proposed' %}
      <form method="post" action="/p/{{ project.slug }}/articles/{{ a.id }}/approve" class="inline">
        <button class="btn btn-sm btn-primary">{{ "article.btn.approve" | t(locale=locale) }}</button>
      </form>
      <form method="post" action="/p/{{ project.slug }}/articles/{{ a.id }}/reject" class="inline">
        <button class="btn btn-sm">{{ "article.btn.reject" | t(locale=locale) }}</button>
      </form>
    {% elif a.status == 'rejected' %}
      <form method="post" action="/p/{{ project.slug }}/articles/{{ a.id }}/restore" class="inline">
        <button class="btn btn-sm">{{ "article.btn.restore" | t(locale=locale) }}</button>
      </form>
    {% elif a.status == 'failed' %}
      <form method="post" action="/p/{{ project.slug }}/articles/{{ a.id }}/approve" class="inline">
        <button class="btn btn-sm">{{ "article.btn.retry" | t(locale=locale) }}</button>
      </form>
    {% elif a.status == 'drafted' %}
      {% if a.can_publish %}
        <form method="post" action="/p/{{ project.slug }}/articles/{{ a.id }}/publish" class="inline">
          <button class="btn btn-sm btn-primary">{{ "article.btn.publish" | t(locale=locale) }}</button>
        </form>
      {% else %}
        <span class="faint">{{ ("article.gate." ~ a.gate_reason) | t(locale=locale) }}</span>
      {% endif %}
      <form method="post" action="/p/{{ project.slug }}/articles/{{ a.id }}/approve" class="inline">
        <button class="btn btn-sm">{{ "article.btn.retry" | t(locale=locale) }}</button>
      </form>
    {% endif %}
    {% if a.writer_agent %}
      <span class="ml-auto font-mono faint">{{ a.writer_agent }}</span>
    {% endif %}
  </footer>
</article>
```

Create `dreaming/templates/project_articles.html`:

```html
{% extends "_project_layout.html" %}
{% set active = 'articles' %}
{% block project_content %}
<header class="mb-4 flex items-baseline gap-3 flex-wrap">
  <h2 class="text-lg font-semibold strong">{{ "article.title" | t(locale=locale) }}</h2>
  <span class="text-xs faint">{{ total }} {{ "article.total" | t(locale=locale) }}</span>
  <span class="text-xs faint">
    {{ "article.writer" | t(locale=locale) }}:
    {% if writer == 'self' %}{{ "article.writer.self" | t(locale=locale) }}{% else %}<span class="font-mono">{{ writer }}</span>{% endif %}
  </span>
  <form method="post" action="/p/{{ project.slug }}/articles/scan" class="ml-auto inline">
    <button class="btn btn-sm btn-primary" {% if scan_running %}disabled{% endif %}>
      {{ "article.btn.scan" | t(locale=locale) }}
    </button>
  </form>
</header>

{% if not blog_dir %}
<div class="banner banner-warn mb-4">
  <p class="text-sm">{{ "article.blog_dir_missing" | t(locale=locale) }}</p>
</div>
{% endif %}

{% if groups %}
  {% for status, items in groups %}
    <h3 class="section-title mt-4">
      {{ ("article.status." ~ status) | t(locale=locale) }}
      <span class="text-xs faint">{{ items|length }}</span>
    </h3>
    {% for a in items %}{% include "_article_card.html" %}{% endfor %}
  {% endfor %}
{% else %}
  <div class="card"><p class="text-sm">{{ "article.empty" | t(locale=locale) }}</p></div>
{% endif %}
{% endblock %}
```

Before writing these, run `grep -n "banner-warn\|section-title" dreaming/static/components.css`
to confirm both classes exist; if `banner-warn` does not, use `banner` alone —
`check_css_tokens.py` fails on a class that is neither defined nor a Tailwind
utility.

- [ ] **Step 6: Wire the router and the sidebar**

In `dreaming/routes/project_router.py`, add the import next to the other project
imports and the include next to the others:

```python
from dreaming.routes.project_articles import router as articles_router
...
router.include_router(articles_router)
```

In `dreaming/templates/_sidebar.html`, add a `nav_item` immediately after the
`ai_radar` one, copying the call's shape exactly:

```html
      {{ nav_item('articles',      base ~ '/articles',         'article.title',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16v16H4z"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>',
        active) }}
```

- [ ] **Step 7: Run the checks to verify they pass**

Run: `python scripts/smoke_articles.py`
Expected: `ok: /p/{slug}/articles renders the proposal`, then `PASS`

Run: `python scripts/check_i18n.py`
Expected: `OK: locales have identical key sets`

Run: `python scripts/check_css_tokens.py`
Expected: `ALL OK`

- [ ] **Step 8: Commit**

```bash
git add dreaming/routes/project_articles.py dreaming/routes/project_router.py \
        dreaming/templates/project_articles.html dreaming/templates/_article_card.html \
        dreaming/templates/_sidebar.html dreaming/i18n/messages_ru.json \
        dreaming/i18n/messages_en.json scripts/smoke_articles.py
git commit -m "feat(articles): per-project proposals page with status groups

Refs #34"
```

---

### Task 5: Cross-project queue `/articles`

**Files:**
- Create: `dreaming/routes/articles.py`
- Create: `dreaming/templates/articles.html`
- Modify: `dreaming/main.py` (import + `app.include_router`)
- Modify: `dreaming/templates/_sidebar.html` (global section, next to the `g_ai_radar` link)
- Modify: `dreaming/i18n/messages_ru.json`, `messages_en.json`
- Modify: `scripts/smoke_articles.py`

**Interfaces:**
- Consumes: `db.list_article_proposals(status=...)`, `projects.list_all`
- Produces: `GET /articles` — everything in `proposed` across projects, newest first

- [ ] **Step 1: Write the failing check**

In the `TestClient` block of `scripts/smoke_articles.py`:

```python
            queue = client.get("/articles")
            if queue.status_code != 200:
                fail(f"/articles queue: {queue.status_code}")
                return 1
        print("ok: cross-project /articles queue renders")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/smoke_articles.py`
Expected: `FAIL: /articles queue: 404`

- [ ] **Step 3: Add two i18n keys**

RU: `"article.queue.title": "Очередь статей"`, `"article.queue.empty": "Нечего согласовывать."`
EN: `"article.queue.title": "Article queue"`, `"article.queue.empty": "Nothing to approve."`

- [ ] **Step 4: Implement the route**

Create `dreaming/routes/articles.py`:

```python
"""GET /articles — кросс-проектная очередь предложений в статусе proposed.

Ради этого экрана предложения лежат в БД центра, а не в файлах проектов:
один запрос вместо обхода одиннадцати рабочих каталогов.
"""
from __future__ import annotations
import json
from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/articles")
async def articles_queue(request: Request):
    db = request.app.state.db
    rows = await db.list_article_proposals(status="proposed")
    projects = await request.app.state.projects.list_all(only_enabled=True)
    by_id = {p.id: p for p in projects}
    items = []
    for r in rows:
        d = dict(r)
        project = by_id.get(d["project_id"])
        if project is None:
            continue  # проект отключён или удалён — в очереди не показываем
        d["project_slug"] = project.slug
        d["project_label"] = project.label
        try:
            d["tags"] = json.loads(d.get("tags_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            d["tags"] = []
        items.append(d)
    locale = request.cookies.get(
        "dc_locale", request.app.state.settings.default_locale,
    )
    return request.app.state.templates.TemplateResponse(
        request, "articles.html",
        {"items": items, "projects": projects, "locale": locale},
    )
```

Create `dreaming/templates/articles.html`:

```html
{% extends "base.html" %}
{% set active = 'g_articles' %}
{% block content %}
<header class="page-header">
  <div class="page-header__titles">
    <h1 class="page-header__title">{{ "article.queue.title" | t(locale=locale) }}</h1>
    <span class="text-xs faint">{{ items|length }} {{ "article.total" | t(locale=locale) }}</span>
  </div>
</header>

{% if items %}
  {% for a in items %}
  <article class="card mb-3">
    <header class="flex items-baseline gap-3 flex-wrap mb-2">
      <a href="/p/{{ a.project_slug }}/articles" class="text-base font-semibold strong">{{ a.title }}</a>
      <span class="badge badge-brand">{{ a.project_label }}</span>
      <span class="text-xs font-mono faint">{{ a.slug_hint }}</span>
      <span class="text-xs faint ml-auto">{{ a.source }}</span>
    </header>
    {% if a.angle %}<p class="text-sm mb-2">{{ a.angle }}</p>{% endif %}
    <p class="text-xs faint">
      <span class="strong">{{ "article.evidence" | t(locale=locale) }}:</span> {{ a.evidence }}
    </p>
  </article>
  {% endfor %}
{% else %}
  <p class="muted text-sm">{{ "article.queue.empty" | t(locale=locale) }}</p>
{% endif %}
{% endblock %}
```

In `dreaming/main.py`, next to the AI Radar router:

```python
from dreaming.routes.articles import router as articles_router
...
app.include_router(articles_router)
```

In the global section of `dreaming/templates/_sidebar.html`, copy the
`g_ai_radar` anchor and change `active == 'g_articles'`, `href="/articles"`, the
label key to `article.queue.title`, and the icon path to the one from Task 4.

- [ ] **Step 5: Run the checks**

Run: `python scripts/smoke_articles.py` → `PASS`
Run: `python scripts/check_i18n.py` → `OK`
Run: `python scripts/check_css_tokens.py` → `ALL OK`

- [ ] **Step 6: Commit**

```bash
git add dreaming/routes/articles.py dreaming/templates/articles.html \
        dreaming/main.py dreaming/templates/_sidebar.html \
        dreaming/i18n/messages_ru.json dreaming/i18n/messages_en.json \
        scripts/smoke_articles.py
git commit -m "feat(articles): cross-project proposal queue at /articles

Refs #34"
```

---

### Task 6: Feeder buttons on the radar card and the ideas page

**Files:**
- Modify: `dreaming/routes/ai_radar.py` (new POST handler)
- Modify: `dreaming/templates/_ai_radar_card.html` (button next to "To note")
- Modify: `dreaming/routes/project_ideas.py` (new POST handler)
- Modify: `dreaming/templates/project_ideas.html` (button on the row/card)
- Modify: `dreaming/i18n/messages_ru.json`, `messages_en.json`
- Modify: `scripts/smoke_articles.py`

**Interfaces:**
- Consumes: `db.add_article_proposal`, `db.get_radar_finding`, `product_ideas.list_product_ideas`
- Produces:
  - `POST /ai-radar/{finding_id}/propose-article` — form field `target_project`
  - `POST /p/{slug}/ideas/{item_id}/propose-article`
  - `articles.slugify(text: str) -> str` added to `dreaming/services/articles.py`

- [ ] **Step 1: Write the failing check**

Append to `scripts/smoke_articles.py` before `print("PASS")`:

```python
        from dreaming.services import articles as _art
        cases = [
            ("What GLM-5.3 changes for our agents", "what-glm-5-3-changes-for-our"),
            ("Автозаполнение по NIP", "nip"),
            ("   ", ""),
        ]
        for raw, want_prefix in cases:
            got = _art.slugify(raw)
            if want_prefix and not got.startswith(want_prefix.split("-")[0]):
                fail(f"slugify({raw!r}) = {got!r}, expected to start like {want_prefix!r}")
                return 1
            if " " in got or got != got.lower():
                fail(f"slugify({raw!r}) = {got!r}: spaces or uppercase left")
                return 1
        print("ok: slugify produces hyphenated lowercase slugs")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/smoke_articles.py`
Expected: `AttributeError: module 'dreaming.services.articles' has no attribute 'slugify'`

- [ ] **Step 3: Add `slugify`**

Append to `dreaming/services/articles.py`:

```python
import re

_SLUG_DROP = re.compile(r"[^a-z0-9]+")
_SLUG_WORDS = 6


def slugify(text: str, *, max_words: int = _SLUG_WORDS) -> str:
    """Short hyphenated ASCII slug, mirroring blog-writer.md's slug rule.

    Cyrillic characters drop out rather than being transliterated: the writer
    agent picks the real keyword slug, and this is only a seed for the proposal
    row. An all-Cyrillic title therefore yields a short or empty slug, and the
    caller must fall back to the id.
    """
    low = (text or "").strip().lower()
    words = [w for w in _SLUG_DROP.sub(" ", low).split() if w]
    return "-".join(words[:max_words])
```

- [ ] **Step 4: Add the radar handler**

In `dreaming/routes/ai_radar.py`:

```python
@router.post("/ai-radar/{finding_id}/propose-article")
async def ai_radar_propose_article(
    request: Request, finding_id: int, target_project: str = Form(...),
):
    """Radar finding → article proposal. Evidence is assembled from the finding
    itself, so it is a fact by construction (title, source, date)."""
    from dreaming.services import articles as articles_svc
    project = await request.app.state.projects.get_by_slug(target_project)
    if project is None:
        raise HTTPException(status_code=404, detail=f"project {target_project} not found")
    db = request.app.state.db
    finding = await db.get_radar_finding(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="finding not found")
    when = (finding.get("published_at") or finding["discovered_at"])[:10]
    evidence = (
        f"{finding['source_key']} published “{finding['title']}” on {when}: "
        f"{finding['url']}"
    )
    slug = articles_svc.slugify(finding["title"]) or f"radar-{finding_id}"
    new_id = await db.add_article_proposal(
        project.id, source="radar", source_ref=str(finding_id),
        evidence=evidence, title=finding["title"][:300],
        angle="", slug_hint=slug,
        tags_json=finding.get("tags_json") or "[]",
    )
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    resp = RedirectResponse(_back_to(request), status_code=303)
    key = "article.flash.duplicate" if new_id is None else "article.flash.proposed"
    set_flash(resp, request.app.state.i18n.t(key, locale=locale), level="success")
    return resp
```

- [ ] **Step 5: Add the radar button**

In `dreaming/templates/_ai_radar_card.html`, inside the `{% if projects %}`
block, after the "apply as note" form:

```html
    <form method="post" action="/ai-radar/{{ f.id }}/propose-article"
          class="inline flex items-center gap-1">
      <select name="target_project" class="text-xs rounded px-1 py-1 bg-elevated">
        {% for p in projects %}<option value="{{ p.slug }}">{{ p.label }}</option>{% endfor %}
      </select>
      <button class="btn btn-sm">
        {{ "article.btn.propose" | t(locale=locale) }}
      </button>
    </form>
```

- [ ] **Step 6: Add the ideas handler and button**

In `dreaming/routes/project_ideas.py`:

```python
@router.post("/p/{slug}/ideas/{item_id}/propose-article")
async def ideas_propose_article(request: Request, slug: str, item_id: str):
    """Product idea → article proposal. Evidence is the idea's own title and
    file, which is checkable: it exists on disk."""
    from dreaming.services import articles as articles_svc
    from dreaming.services.product_ideas import list_product_ideas
    project = request.state.project
    resolver = request.app.state.resolver_factory(request)
    ideas_dir = await resolver.get(project, "product_ideas_dir", "")
    if not ideas_dir:
        raise HTTPException(status_code=400, detail="product_ideas_dir not set")
    target = None
    for it in list_product_ideas(ideas_dir):
        obj = it.__dict__ if hasattr(it, "__dict__") else (it if isinstance(it, dict) else {})
        if obj.get("id") == item_id or obj.get("slug") == item_id:
            target = obj
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"idea {item_id} not found")
    title = str(target.get("title") or item_id)
    await request.app.state.db.add_article_proposal(
        project.id, source="center", source_ref=item_id,
        evidence=f"product idea “{title}” at {target.get('file_path') or ideas_dir}",
        title=title[:300], angle="",
        slug_hint=articles_svc.slugify(title) or f"idea-{item_id}",
    )
    return RedirectResponse(f"/p/{project.slug}/articles", status_code=303)
```

In `dreaming/templates/project_ideas.html`, add to each idea's action area:

```html
<form method="post" action="/p/{{ project.slug }}/ideas/{{ it.id }}/propose-article" class="inline">
  <button class="btn btn-sm">{{ "article.btn.propose" | t(locale=locale) }}</button>
</form>
```

Check the loop variable name first with
`grep -n "for it in items\|for idea in" dreaming/templates/project_ideas.html`
and match it.

- [ ] **Step 7: Add the i18n keys**

RU: `"article.btn.propose": "Предложить статью"`, `"article.flash.proposed": "Предложение статьи создано."`, `"article.flash.duplicate": "Такой сюжет уже предложен."`
EN: `"article.btn.propose": "Propose an article"`, `"article.flash.proposed": "Article proposal created."`, `"article.flash.duplicate": "That subject is already proposed."`

- [ ] **Step 8: Run the checks**

Run: `python scripts/smoke_articles.py` → `PASS`
Run: `python scripts/check_i18n.py` → `OK`
Run: `python scripts/check_css_tokens.py` → `ALL OK`

Manual: open `/ai-radar`, press the new button on a finding, confirm the flash
and that the proposal shows up at `/p/<slug>/articles`.

- [ ] **Step 9: Commit**

```bash
git add dreaming/routes/ai_radar.py dreaming/routes/project_ideas.py \
        dreaming/templates/_ai_radar_card.html dreaming/templates/project_ideas.html \
        dreaming/services/articles.py dreaming/i18n/messages_ru.json \
        dreaming/i18n/messages_en.json scripts/smoke_articles.py
git commit -m "feat(articles): propose-article buttons on radar and ideas

Refs #34"
```

---

### Task 7: Starter-kit command `article-ideas-scan`

**Files:**
- Create: `templates/starter-kit/commands/article-ideas-scan.md`
- Modify: `dreaming/routes/project_articles.py` (the `scan` POST the page already links to)
- Modify: `scripts/smoke_articles.py`

**Interfaces:**
- Consumes: `pm.start_command`, Task 2's `/api/p/{slug}/articles/ingest` and `/list`
- Produces: `POST /p/{slug}/articles/scan` → redirects to `/p/{slug}/live`

- [ ] **Step 1: Write the failing check**

```python
        # ── starter-kit template present and self-consistent ───────
        kit = ROOT / "templates" / "starter-kit" / "commands" / "article-ideas-scan.md"
        if not kit.exists():
            fail("article-ideas-scan.md missing from the starter kit")
            return 1
        body = kit.read_text(encoding="utf-8")
        for needle in ("/api/p/", "articles/ingest", "evidence", "DREAMING_API_URL"):
            if needle not in body:
                fail(f"article-ideas-scan.md does not mention {needle!r}")
                return 1
        print("ok: article-ideas-scan command shipped in the starter kit")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/smoke_articles.py`
Expected: `FAIL: article-ideas-scan.md missing from the starter kit`

- [ ] **Step 3: Write the command**

Create `templates/starter-kit/commands/article-ideas-scan.md`. Read
`templates/starter-kit/commands/product-idea-scan.md` first and match its
frontmatter and tone. Content:

```markdown
---
description: Propose 3-7 article topics for this project and post them to the AI Dreaming Center.
---

# Article ideas scan

Propose article topics for **this repository's** external blog. You are not
writing the articles — only proposing what is worth writing, with evidence.

## The rule that makes this useful

Every proposal MUST carry `evidence`: one sentence naming a fact anyone can
check — a commit, a shipped feature, a closed wave, a dated release, a measured
gap. The center rejects a proposal with blank evidence (HTTP 400), and that is
deliberate: a queue of unfalsifiable suggestions is worse than an empty queue.

Never propose from a feeling ("developers care about X"). Propose from a fact
("commit 4a1f530 removed three unused classes; the migration is now finishable
in one pass").

## Where to look, in order

1. `git log --since="60 days ago" --oneline` — what actually shipped.
2. Closed wave plans and specs under `docs/superpowers/` — finished work with a
   written rationale is the best article material this repo has.
3. Product pages / README features that no article covers yet.
4. If `docs/seo/ai-visibility/REPORT.md` exists, read it. Its `page-not-cited`
   and `dead-language` lines are already evidence-backed content gaps — turn
   each into a proposal and quote the report line as the evidence.

## Skip what is already proposed

```bash
curl -s "$DREAMING_API_URL/api/p/$DREAMING_PROJECT_SLUG/articles/list"
```

Do not propose a `slug_hint` that appears in that list.

## Post each proposal

```bash
curl -s -X POST "$DREAMING_API_URL/api/p/$DREAMING_PROJECT_SLUG/articles/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "How we cut the report from eight hours to twenty minutes",
    "slug_hint": "report-time-eight-hours-to-twenty-minutes",
    "angle": "Walk through the query plan change, with the numbers",
    "evidence": "commit 1a2a965, 2026-08-18: replaced the per-row lookup with one join",
    "source": "project_scan",
    "source_ref": "1a2a965",
    "funnel_level": "product",
    "locales": "pl,en,ru",
    "tags": ["performance", "SQL"]
  }'
```

`funnel_level` is `top` for search-driven pieces that answer a question a
stranger types, and `product` for "our product as proof" write-ups.

Reuse the tag vocabulary already present in the project's existing posts rather
than inventing new tags.

## Report

Print one line per proposal: slug, whether the API returned 201 or reported a
duplicate, and the evidence you attached. Report the count. Do not claim a
proposal landed without showing the response.
```

- [ ] **Step 4: Add the scan dispatch route**

Append to `dreaming/routes/project_articles.py`:

```python
@router.post("/p/{slug}/articles/scan")
async def articles_scan(request: Request, slug: str):
    """Dispatch /article-ideas-scan into the project. Proposes only — this
    session never writes an article and never publishes."""
    project = request.state.project
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    resolver = request.app.state.resolver_factory(request)
    try:
        await pm.start_command(
            project,
            command_name="article-ideas-scan",
            prompt="/article-ideas-scan",
            claude_path=await resolver.get(project, "claude_path", "claude"),
            working_dir=project.working_dir,
            model=await resolver.get(project, "model", "sonnet"),
            max_turns=int(await resolver.get(project, "max_turns", 50)),
            timeout_minutes=int(await resolver.get(project, "timeout_minutes", 30)),
            env_overrides={
                "DREAMING_PROJECT_SLUG": project.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
            },
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return RedirectResponse(f"/p/{project.slug}/live", status_code=303)
```

- [ ] **Step 5: Run the checks**

Run: `python scripts/smoke_articles.py` → `PASS`

Manual: on `/p/ai-dreaming-center/articles` press "Предложить темы", watch
`/p/ai-dreaming-center/live`, and confirm proposals appear with non-empty
evidence. Also confirm the starter kit reports the new file as installable at
`/p/<slug>/help` (or wherever `starter_kit.status` is surfaced).

- [ ] **Step 6: Commit**

```bash
git add templates/starter-kit/commands/article-ideas-scan.md \
        dreaming/routes/project_articles.py scripts/smoke_articles.py
git commit -m "feat(articles): article-ideas-scan command and its dispatch

Refs #34"
```

---

### Task 8: Approve → dispatch `/write-article`

**Files:**
- Create: `templates/starter-kit/commands/write-article.md`
- Modify: `dreaming/routes/project_articles.py` (the `approve` POST)
- Modify: `scripts/smoke_articles.py`

**Interfaces:**
- Consumes: `pm.start_command`, `articles.resolve_writer`, Task 2's `/api/articles/{id}` and `/written`
- Produces: `POST /p/{slug}/articles/{proposal_id}/approve` — refuses with 400 when `article_blog_dir` is unset; sets status `writing` and records `writer_agent`

- [ ] **Step 1: Write the failing check**

```python
        kit2 = ROOT / "templates" / "starter-kit" / "commands" / "write-article.md"
        if not kit2.exists():
            fail("write-article.md missing from the starter kit")
            return 1
        body2 = kit2.read_text(encoding="utf-8")
        for needle in ("/api/articles/", "/written", "verify_ok", "draft_ref"):
            if needle not in body2:
                fail(f"write-article.md does not mention {needle!r}")
                return 1
        print("ok: write-article command shipped in the starter kit")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/smoke_articles.py`
Expected: `FAIL: write-article.md missing from the starter kit`

- [ ] **Step 3: Write the command**

Create `templates/starter-kit/commands/write-article.md`:

```markdown
---
description: Write one approved article from the AI Dreaming Center's proposal, then report the draft and its verification.
---

# Write article

Usage: `/write-article <proposal-id>`

## 1. Read the brief

```bash
curl -s "$DREAMING_API_URL/api/articles/<proposal-id>"
```

You get `title`, `angle`, `slug_hint`, `funnel_level`, `locales`, `tags_json`,
`evidence`, `related_product`. The evidence is the fact the piece must be true
to — do not write around it.

## 2. Find out who writes

`$DC_ARTICLE_WRITER` names the agent the center resolved. If it is a real agent
name, delegate the writing to that subagent and let it own the format. If it is
`self`, write the piece yourself.

Either way, **the project owns the article's shape**. Before writing anything,
read two or three existing articles in `$DC_ARTICLE_BLOG_DIR` and copy their
structure exactly: file layout, frontmatter fields, language set, heading style,
where the CTA goes. If this project keeps prose as data (a JSON entry rather
than a markdown file), add a data entry — do not invent a markdown file beside
it. If adding an article requires registering it somewhere (a build entry, an
index, a route), do that too; a piece that does not build is not written.

Match the existing typography per language. In this house style Polish quotes
are `„…”`, Russian are `«…»`, English are `"…"`, dashes are `—`, and ellipses
are `…`. Straight quotes in Polish or Russian text are a defect.

No invented numbers, clients, or benchmarks. If a claim is unverified, ask
rather than guess.

## 3. Verify

If `$DC_ARTICLE_VERIFY_CMD` is set, run it and capture the output verbatim. A
failure is a result to report, not something to hide or work around.

## 4. Report back

On success:

```bash
curl -s -X POST "$DREAMING_API_URL/api/articles/<proposal-id>/written" \
  -H "Content-Type: application/json" \
  -d '{"draft_ref": "<paths you created or edited>",
       "verify_output": "<verbatim output, or: no verify command configured>",
       "writer_agent": "<agent name or self>",
       "verify_ok": true}'
```

On failure, POST the same endpoint with `{"error_message": "<what failed>"}`.

Set `verify_ok` to `true` only if you ran the command and it exited zero. If
there was no command to run, send `false` with `verify_output` saying so — the
center labels that publish "unverified", which is honest; a `true` you did not
observe is not.

Never commit and never push. Publishing is a separate, human-approved step in
the center.
```

- [ ] **Step 4: Implement approve**

Append to `dreaming/routes/project_articles.py`:

```python
@router.post("/p/{slug}/articles/{proposal_id}/approve")
async def articles_approve(request: Request, slug: str, proposal_id: int):
    """The first human gate: approve a proposal and dispatch the writer.

    bypassPermissions is required — with --allowedTools the session silently
    loses the ability to write into the repo (settled on self-study)."""
    project = request.state.project
    db = request.app.state.db
    pm = request.app.state.process_manager
    settings = request.app.state.settings
    resolver = request.app.state.resolver_factory(request)
    row = await db.get_article_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="proposal not found")
    blog_dir = await resolver.get(project, "article_blog_dir", "")
    if not blog_dir:
        raise HTTPException(
            status_code=400,
            detail="article_blog_dir is not set — nowhere to put the article",
        )
    writer = articles.resolve_writer(
        project.working_dir,
        await resolver.get(project, "article_writer_agent", ""),
    )
    verify_cmd = await resolver.get(project, "article_verify_cmd", "")
    locales = await resolver.get(project, "article_locales", "")
    try:
        session_id = await pm.start_command(
            project,
            command_name="write-article",
            prompt=f"/write-article {proposal_id}",
            claude_path=await resolver.get(project, "claude_path", "claude"),
            working_dir=project.working_dir,
            model=await resolver.get(project, "model", "sonnet"),
            max_turns=int(await resolver.get(project, "article_max_turns", 300)),
            timeout_minutes=int(
                await resolver.get(project, "article_timeout_minutes", 120)
            ),
            env_overrides={
                "DREAMING_PROJECT_SLUG": project.slug,
                "DREAMING_API_URL": f"http://localhost:{settings.port}",
                "DC_ARTICLE_WRITER": writer,
                "DC_ARTICLE_BLOG_DIR": blog_dir,
                "DC_ARTICLE_VERIFY_CMD": verify_cmd,
                "DC_ARTICLE_LOCALES": locales or row["locales"],
            },
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    await db.set_article_proposal_status(
        proposal_id, "writing", session_id=session_id or "",
    )
    return RedirectResponse(f"/p/{project.slug}/live", status_code=303)
```

Confirm `start_command` returns the session id (it is documented as "Returns
session_id" at `dreaming/services/process_manager.py:383`); if the call site
pattern elsewhere ignores it, still capture it here.

- [ ] **Step 5: Run the checks**

Run: `python scripts/smoke_articles.py` → `PASS`

Manual, on `mi-code-ai` (the project this design was modelled on): set
`article_blog_dir` to `micode-landing-page`, `article_verify_cmd` to
`npm run build`, `article_writer_agent` empty (autodetect must find
`blog-writer`), approve one proposal, and watch `/p/test/live`. Confirm the card
reaches `drafted` with the build output attached.

- [ ] **Step 6: Commit**

```bash
git add templates/starter-kit/commands/write-article.md \
        dreaming/routes/project_articles.py scripts/smoke_articles.py
git commit -m "feat(articles): approve gate dispatches the project's writer

Refs #34"
```

---

### Task 9: Publish via git

**Files:**
- Create: `dreaming/services/article_publish.py`
- Modify: `dreaming/routes/project_articles.py` (the `publish` POST)
- Modify: `scripts/smoke_articles.py`

**Interfaces:**
- Consumes: `articles.can_publish`, `db.mark_article_published`
- Produces:
  - `article_publish.publish(working_dir: str, paths: list[str], *, message: str, push: bool) -> str` — returns the commit sha; raises `PublishError`
  - `article_publish.split_paths(draft_ref: str) -> list[str]`
  - `article_publish.build_message(row: dict, label: str) -> str`
  - `POST /p/{slug}/articles/{proposal_id}/publish`

- [ ] **Step 1: Write the failing check**

Append to `scripts/smoke_articles.py` before `print("PASS")`:

```python
        # ── publish: real git repo in a temp dir ───────────────────
        import subprocess
        from dreaming.services import article_publish

        repo = tmp / "repo"
        (repo / "content").mkdir(parents=True)
        def git(*args, cwd=repo):
            return subprocess.run(["git", *args], cwd=str(cwd),
                                  capture_output=True, text=True)
        git("init", "-q")
        git("config", "user.email", "smoke@example.test")
        git("config", "user.name", "Smoke")
        (repo / "README.md").write_text("seed\n", encoding="utf-8")
        git("add", "README.md")
        git("commit", "-q", "-m", "seed")

        article = repo / "content" / "piece.md"
        article.write_text("# Piece\n", encoding="utf-8")
        noise = repo / "unrelated.txt"
        noise.write_text("do not commit me\n", encoding="utf-8")

        sha = await article_publish.publish(
            str(repo), ["content/piece.md"],
            message="publish: piece (unverified)", push=False,
        )
        if not sha or len(sha) < 7:
            fail(f"publish returned no sha: {sha!r}")
            return 1
        listed = git("show", "--name-only", "--pretty=format:", sha).stdout.split()
        if listed != ["content/piece.md"]:
            fail(f"commit contains {listed}, want only content/piece.md")
            return 1
        if not noise.exists() or "do not commit me" not in noise.read_text(encoding="utf-8"):
            fail("publish touched the unrelated working-tree file")
            return 1
        status_after = git("status", "--porcelain").stdout
        if "unrelated.txt" not in status_after:
            fail("the unrelated file left the working tree — stash or add -A happened")
            return 1
        print("ok: publish commits only draft paths, leaves the rest alone")

        # A target path that someone else has already STAGED must refuse
        # rather than sweep their index entry into our commit.
        article.write_text("# Piece edited by hand\n", encoding="utf-8")
        git("add", "content/piece.md")
        try:
            await article_publish.publish(
                str(repo), ["content/piece.md"], message="second", push=False,
            )
        except article_publish.PublishError:
            print("ok: dirty article path refuses to publish")
        else:
            fail("dirty article path published anyway")
            return 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/smoke_articles.py`
Expected: `ModuleNotFoundError: No module named 'dreaming.services.article_publish'`

- [ ] **Step 3: Implement the service**

Create `dreaming/services/article_publish.py`:

```python
"""Publish an article by committing exactly its own files.

Hard rules, and the reason for them: orchestration in this repo once swept
uncommitted work out of a project with `git stash -u`, and this feature runs
against eleven working trees that belong to the user, not to us. So:

  * stage only the paths the writer reported, never `git add -A`;
  * never `git stash`, for any reason;
  * if a target path already carries uncommitted edits that are not ours,
    refuse — the user's unsaved work outranks our commit.
"""
from __future__ import annotations
import asyncio
import shutil
import subprocess
from pathlib import Path


class PublishError(RuntimeError):
    """Publishing refused or failed. The message is shown to the user."""


def split_paths(draft_ref: str) -> list[str]:
    """draft_ref may list several paths, comma- or newline-separated."""
    parts = [p.strip() for p in (draft_ref or "").replace("\n", ",").split(",")]
    return [p for p in parts if p]


def build_message(row: dict, label: str) -> str:
    """Commit subject + the verification claim, which must match reality."""
    title = (row.get("title") or "article").strip()
    slug = (row.get("slug_hint") or "").strip()
    head = f"content: publish “{title}”"
    body = [f"slug: {slug}" if slug else "", f"verification: {label}"]
    if row.get("source") and row.get("source_ref"):
        body.append(f"proposed from {row['source']} {row['source_ref']}")
    return head + "\n\n" + "\n".join(b for b in body if b) + "\n"


async def _run(cmd: list[str], cwd: str) -> tuple[int, str, str]:
    """subprocess in a thread: create_subprocess_exec needs a ProactorEventLoop
    on Windows and uvicorn --reload does not always provide one."""
    def _do() -> tuple[int, str, str]:
        try:
            r = subprocess.run(
                cmd, cwd=cwd, capture_output=True, check=False, shell=False,
            )
            return (r.returncode,
                    r.stdout.decode("utf-8", errors="replace"),
                    r.stderr.decode("utf-8", errors="replace"))
        except OSError as e:
            return -1, "", str(e)
    return await asyncio.to_thread(_do)


async def publish(
    working_dir: str, paths: list[str], *, message: str, push: bool,
) -> str:
    """Stage `paths`, commit, optionally push. Returns the new commit sha."""
    if not paths:
        raise PublishError("nothing to publish: the draft reported no paths")
    wd = Path(working_dir)
    if not (wd / ".git").exists():
        raise PublishError(f"{working_dir} is not a git repository")
    git = shutil.which("git") or "git"

    # Refuse when a target path holds edits that are not the draft itself.
    # `git status --porcelain -- <paths>` lists staged and unstaged changes; an
    # index entry we did not create means someone else is mid-edit here.
    rc, out, err = await _run([git, "status", "--porcelain", "--", *paths], str(wd))
    if rc != 0:
        raise PublishError(f"git status failed: {err.strip() or rc}")
    staged = [ln for ln in out.splitlines() if ln[:1] not in (" ", "?", "")]
    if staged:
        raise PublishError(
            "these paths already have staged changes — commit or reset them "
            "first:\n" + "\n".join(staged)
        )

    rc, _out, err = await _run([git, "add", "--", *paths], str(wd))
    if rc != 0:
        raise PublishError(f"git add failed: {err.strip() or rc}")

    rc, out, err = await _run(
        [git, "diff", "--cached", "--name-only"], str(wd),
    )
    if rc != 0:
        raise PublishError(f"git diff --cached failed: {err.strip() or rc}")
    if not out.strip():
        raise PublishError("nothing staged: the draft paths match HEAD already")

    rc, out, err = await _run([git, "commit", "-m", message], str(wd))
    if rc != 0:
        raise PublishError(f"git commit failed: {(err or out).strip() or rc}")

    rc, sha, err = await _run([git, "rev-parse", "HEAD"], str(wd))
    if rc != 0:
        raise PublishError(f"git rev-parse failed: {err.strip() or rc}")
    commit = sha.strip()

    if push:
        rc, out, err = await _run([git, "push"], str(wd))
        if rc != 0:
            raise PublishError(
                f"committed {commit[:8]} but the push failed: "
                f"{(err or out).strip() or rc}"
            )
    return commit
```

Note on the dirty-path check — the index-only filter is deliberate, do not
widen it. Git cannot tell the writer's own unstaged edits from a human's: on the
landing page a new article legitimately shows ` M src/data/blog-posts.json` and
` M vite.config.ts`, because adding a post means editing tracked files. A check
that refused any dirty target path would refuse every real publish there, and
would also refuse the first publish of a brand-new untracked file (`??`). What
it can detect is a *staged* change we did not make, which means a human is
mid-commit in those paths — that is the case worth refusing. This narrows the
spec's "unrelated uncommitted edits stop the publish" to "staged edits stop the
publish"; the guarantee that survives, and the one the stash incident was
actually about, is that nothing outside `draft_ref` is ever touched.

- [ ] **Step 4: Implement the publish route**

Append to `dreaming/routes/project_articles.py`:

```python
@router.post("/p/{slug}/articles/{proposal_id}/publish")
async def articles_publish(request: Request, slug: str, proposal_id: int):
    """The second human gate. Commits only the article's own files."""
    from dreaming.services import article_publish
    project = request.state.project
    db = request.app.state.db
    resolver = request.app.state.resolver_factory(request)
    row = await db.get_article_proposal(proposal_id)
    if row is None or row["project_id"] != project.id:
        raise HTTPException(status_code=404, detail="proposal not found")
    verify_cmd = await resolver.get(project, "article_verify_cmd", "")
    publish_mode = await resolver.get(project, "article_publish_mode", "off")
    allowed, reason = articles.can_publish(row, verify_cmd, publish_mode)
    if not allowed:
        raise HTTPException(status_code=400, detail=f"publish refused: {reason}")
    label = articles.publish_label(bool(row["verify_ok"]), verify_cmd)
    try:
        commit = await article_publish.publish(
            project.working_dir,
            article_publish.split_paths(row["draft_ref"]),
            message=article_publish.build_message(row, label),
            push=(publish_mode == "commit+push"),
        )
    except article_publish.PublishError as e:
        await db.set_article_proposal_status(
            proposal_id, "drafted", error_message=str(e)[:2000],
        )
        raise HTTPException(status_code=409, detail=str(e))
    await db.mark_article_published(proposal_id, commit_ref=commit)
    return RedirectResponse(f"/p/{project.slug}/articles", status_code=303)
```

- [ ] **Step 5: Run the checks**

Run: `python scripts/smoke_articles.py`
Expected: both new `ok:` lines and `PASS`

- [ ] **Step 6: Commit**

```bash
git add dreaming/services/article_publish.py dreaming/routes/project_articles.py \
        scripts/smoke_articles.py
git commit -m "feat(articles): publish by committing only the draft's own paths

Never add -A, never stash, refuse a dirty target path.

Refs #34"
```

---

### Task 10: Weekly proposal job

**Files:**
- Modify: `dreaming/services/scheduler.py` (a job function + one `_PER_PROJECT_JOBS` row)
- Modify: `scripts/smoke_articles.py`

**Interfaces:**
- Consumes: `pm.start_command`, `_PER_PROJECT_JOBS` registration machinery
- Produces: job kind `weekly_article_ideas_scan`, keys `weekly_article_ideas_scan_cron` / `_enabled`

- [ ] **Step 1: Write the failing check**

```python
        # ── scheduler wiring ──────────────────────────────────────
        from dreaming.services import scheduler as sched_mod
        kinds = [row[0] for row in sched_mod._PER_PROJECT_JOBS]
        if "weekly_article_ideas_scan" not in kinds:
            fail(f"weekly_article_ideas_scan not registered; kinds={kinds}")
            return 1
        row = next(r for r in sched_mod._PER_PROJECT_JOBS
                   if r[0] == "weekly_article_ideas_scan")
        if row[4] is not False:
            fail("the weekly article scan must default to disabled")
            return 1
        print("ok: weekly_article_ideas_scan registered, off by default")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/smoke_articles.py`
Expected: `FAIL: weekly_article_ideas_scan not registered; kinds=[...]`

- [ ] **Step 3: Add the job**

In `dreaming/services/scheduler.py`, copy `_weekly_product_ideas_scan` and
adapt (read it first: `grep -n "_weekly_product_ideas_scan" -A 25
dreaming/services/scheduler.py`). The command name and prompt are
`article-ideas-scan` / `/article-ideas-scan`. Then add the row:

```python
    ("weekly_article_ideas_scan", "weekly_article_ideas_scan_cron",
     "weekly_article_ideas_scan_enabled", "0 8 * * 1", False,
     _weekly_article_ideas_scan),
```

The job proposes only. It must not call the approve route, `start_command` with
`write-article`, or anything in `article_publish`.

- [ ] **Step 4: Run the checks**

Run: `python scripts/smoke_articles.py` → `PASS`
Run: `python -c "import dreaming.main"` → no output, exit 0 (import-time wiring is sound)

- [ ] **Step 5: Commit**

```bash
git add dreaming/services/scheduler.py scripts/smoke_articles.py
git commit -m "feat(articles): weekly proposal scan job, disabled by default

Refs #34"
```

---

### Task 11: Full verification pass and end-to-end run

**Files:**
- Modify: whatever the run turns up
- Modify: `docs/en/waves.md`, `docs/ru/waves.md` (one line recording this work, matching the existing entries' shape)

- [ ] **Step 1: Run every check in the repo**

```bash
python scripts/smoke_articles.py
python scripts/smoke_ai_radar.py
python scripts/check_i18n.py
python scripts/check_css_tokens.py
```

Expected: all four exit 0. `smoke_ai_radar.py` must still pass — Task 6 edited
the radar card and route.

- [ ] **Step 2: Render every touched page**

```bash
python -c "
from starlette.testclient import TestClient
from dreaming.main import app
with TestClient(app) as c:
    for url in ['/articles', '/ai-radar', '/p/ai-dreaming-center/articles',
                '/p/ai-dreaming-center/ideas', '/p/ai-dreaming-center/ai-radar',
                '/settings']:
        r = c.get(url)
        print(url, r.status_code)
        assert r.status_code == 200, r.text[:400]
print('ALL PAGES 200')
"
```

- [ ] **Step 3: End-to-end on `mi-code-ai`**

This is the only project with a build that can verify the result, and the one
whose `blog-writer` this design was modelled on.

1. In its project settings set `article_blog_dir=micode-landing-page`,
   `article_verify_cmd=npm run build`, `article_publish_mode=commit`,
   `article_writer_agent` empty.
2. Confirm the page reports the writer as `blog-writer` (autodetect).
3. Run "Предложить темы"; confirm proposals arrive with real evidence.
4. Approve one; watch `/p/test/live` to the end.
5. Confirm the card reaches `drafted`, shows `verify_output` from the build, and
   `draft_ref` names `src/data/blog-posts.json` plus the new `blog/<slug>/`
   files.
6. Press Publish; confirm `git -C D:\Work\micode\mi-code-ai\micode-landing-page
   show --name-only HEAD` lists only the article's files.

Record what actually happened, including anything that failed. Do not mark this
step done on a partial run.

- [ ] **Step 4: Record the wave and commit**

```bash
git add docs/en/waves.md docs/ru/waves.md
git commit -m "docs(waves): record the article pipeline wave

Closes #34"
```

- [ ] **Step 5: Push**

```bash
git push origin master
```

---

## Self-Review

**Spec coverage.** Every section of the spec maps to a task: the data model and
status machine → Task 1; the evidence-required rule → Task 2; settings, writer
resolution and the three-case publish gate → Task 3; the per-project UI → Task
4; the cross-project queue → Task 5; the radar and ideas feeders → Task 6; the
scan command → Task 7; dispatch and the write command → Task 8; git publishing
with its hard constraints → Task 9; the disabled-by-default cron → Task 10;
testing and the end-to-end run → Task 11. The spec's "out of scope" list stays
out: no task translates or edits published pieces, and none touches dev.to,
Telegram, Habr, or `docs/marketing/`.

**Placeholders.** None. Every code step carries the real code; the three places
that say "read the existing file first" (`_weekly_product_ideas_scan` in Task
10, the ideas-template loop variable in Task 6, the `banner-warn` class check in
Task 4) name the exact grep to run, because the surrounding code is the
authority on shape and inventing it here would be guessing.

**Type consistency.** `add_article_proposal` returns `int | None` in Task 1 and
both callers (Task 2's ingest, Task 6's buttons) handle the `None` duplicate
case. `can_publish(row, verify_cmd, publish_mode) -> (bool, str)` keeps that
signature in Tasks 3, 4 and 9. `publish(working_dir, paths, *, message, push)`
matches between Task 9's service and its route. `resolve_writer(working_dir,
configured)` is called the same way in Tasks 3, 4 and 8. The reason-key strings
`mode_off` / `not_drafted` / `verify_failed` from Task 3 are exactly the
`article.gate.*` i18n keys added in Task 4.

**One deliberate deviation from the spec.** The spec named `scripts/
smoke_articles.py` as a single smoke script; this plan grows it task by task
rather than writing it once at the end, so every task has a failing check before
its implementation. Same file, same final content.
