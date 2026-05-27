# AI Metrics: Skills & Agents Breakdown — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new cross-sections to the AI-usage metrics pages (per-project and global) — invocation frequency per skill, and token usage per Task subagent.

**Architecture:** A new nullable column `agent_name` on `ai_usage_events` (stamped from each subagent's `meta.json` during ingest) gives clean per-agent token totals. A new table `ai_skill_invocations` (one row per `Skill` tool_use block) gives per-skill call counts. The parser writes both inline during the existing incremental ingest; a one-time startup backfill populates history. Two stats helpers feed two new template sections.

**Tech Stack:** Python 3 / FastAPI / aiosqlite, Jinja2 templates, Chart.js, flat-JSON i18n (RU source of truth, EN mirror).

---

## Repo conventions that override the writing-plans defaults

- **No pytest suite.** Per `CLAUDE.md`, verification is manual `scripts/smoke_*.py` plus inline `python -c` checks and a running server. Tasks below use those, not pytest.
- **Cyrillic files via Write/Edit tool only** (UTF-8). Never `Set-Content` (UTF-16 breaks the parser). This applies to the i18n JSON and templates.
- **Migrations** go in `SqliteDB._migrate_orchestration` (idempotent `PRAGMA table_info` + guarded `ALTER` / `CREATE TABLE IF NOT EXISTS`). A bare `ADD COLUMN` re-run throws "duplicate column".
- Run commands from repo root `D:\Work\micode\ai-dreaming-center`. Server: `python -m uvicorn dreaming.main:app --port 8086 --reload`.

## File map

- Modify `dreaming/services/db.py` — schema migration (Task 1).
- Modify `dreaming/services/ai_usage_stats.py` — `_by_skill`, `_by_agent`, summary keys (Task 2).
- Modify `dreaming/services/ai_usage_parser.py` — helpers + ingest wiring + backfill (Tasks 3–5).
- Modify `dreaming/main.py` — one-time startup backfill hook (Task 5).
- Create `scripts/smoke_skill_agent_stats.py` — end-to-end smoke (Task 6).
- Modify `dreaming/templates/project_ai_usage.html`, `dreaming/templates/global_ai_usage.html` — new section (Task 7).
- Modify `dreaming/i18n/messages_ru.json`, `dreaming/i18n/messages_en.json` — new keys (Task 7).

---

## Task 1: Schema migration

**Files:**
- Modify: `dreaming/services/db.py` (inside `_migrate_orchestration`, after the `orchestrator_questions` block, before the method's closing).

- [ ] **Step 1: Add the migration code**

Append this inside `_migrate_orchestration` (after the `orchestrator_questions` `try/except`, still inside the method):

```python
        # --- ai-metrics: skills & agents breakdown ---
        async with self._conn.execute(
            "PRAGMA table_info(ai_usage_events)"
        ) as cur:
            aue_cols = {row[1] for row in await cur.fetchall()}
        if "agent_name" not in aue_cols:
            try:
                await self._conn.execute(
                    "ALTER TABLE ai_usage_events ADD COLUMN agent_name TEXT"
                )
            except Exception as e:
                log.warning("Failed to add agent_name column: %s", e)

        try:
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_skill_invocations (
                    message_id   TEXT NOT NULL,
                    skill_name   TEXT NOT NULL,
                    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    ts           TEXT NOT NULL,
                    ts_date      TEXT NOT NULL,
                    session_id   TEXT NOT NULL,
                    is_sidechain INTEGER NOT NULL DEFAULT 0,
                    model        TEXT,
                    source_file  TEXT NOT NULL,
                    PRIMARY KEY (message_id, skill_name)
                )
                """
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_skill_inv_proj_date "
                "ON ai_skill_invocations (project_id, ts_date)"
            )
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_skill_inv_name "
                "ON ai_skill_invocations (skill_name, ts_date)"
            )
            await self._conn.commit()
        except Exception as e:
            log.warning("Failed to create ai_skill_invocations: %s", e)
```

- [ ] **Step 2: Verify the migration applies to a fresh and an existing DB**

Run:

```bash
python -c "import asyncio, tempfile, os; from dreaming.services.db import SqliteDB
async def m():
    p = os.path.join(tempfile.mkdtemp(), 't.db')
    db = SqliteDB(p); await db.connect()
    async with db._conn.execute('PRAGMA table_info(ai_usage_events)') as cur:
        cols = [r[1] for r in await cur.fetchall()]
    assert 'agent_name' in cols, cols
    t = await db.fetch_one(\"SELECT name FROM sqlite_master WHERE type='table' AND name='ai_skill_invocations'\")
    assert t is not None
    await db.close()
    # reconnect (simulates existing DB) — must not raise duplicate column
    db = SqliteDB(p); await db.connect(); await db.close()
    print('OK migration idempotent')
asyncio.run(m())"
```

Expected: `OK migration idempotent`

- [ ] **Step 3: Commit**

```bash
git add dreaming/services/db.py
git commit -m "feat(ai-metrics): schema for agent_name + ai_skill_invocations"
```

---

## Task 2: Stats aggregators

**Files:**
- Modify: `dreaming/services/ai_usage_stats.py` (add two helpers near `_by_model`; extend `project_summary` and `global_summary`).

- [ ] **Step 1: Add `_by_skill` and `_by_agent`**

Insert after `_by_project` (around line 136):

```python
async def _by_skill(
    db: SqliteDB,
    *,
    start: str,
    end: str,
    project_id: int | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    """Skill invocation counts in the window, ordered by calls desc."""
    sql = (
        "SELECT skill_name, COUNT(*) AS calls, "
        "COUNT(DISTINCT session_id) AS sessions "
        "FROM ai_skill_invocations "
        "WHERE ts_date BETWEEN ? AND ? "
    )
    params: list[Any] = [start, end]
    if project_id is not None:
        sql += "AND project_id=? "
        params.append(project_id)
    if model:
        sql += "AND model=? "
        params.append(model)
    sql += "GROUP BY skill_name ORDER BY calls DESC, skill_name ASC"
    rows = await db.fetch_all(sql, tuple(params))
    return [dict(r) for r in rows]


async def _by_agent(
    db: SqliteDB,
    *,
    start: str,
    end: str,
    project_id: int | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    """Token totals + run count per Task subagent (agentType), tokens desc."""
    sql = (
        "SELECT agent_name, "
        "COUNT(*) AS events, "
        "COUNT(DISTINCT session_id) AS runs, "
        "COALESCE(SUM(input_tokens+output_tokens+cache_read_tokens+cache_creation_tokens), 0) "
        "  AS total_tokens "
        "FROM ai_usage_events "
        "WHERE ts_date BETWEEN ? AND ? "
        "AND agent_name IS NOT NULL AND agent_name <> '' "
    )
    params: list[Any] = [start, end]
    if project_id is not None:
        sql += "AND project_id=? "
        params.append(project_id)
    if model:
        sql += "AND model=? "
        params.append(model)
    sql += "GROUP BY agent_name ORDER BY total_tokens DESC, agent_name ASC"
    rows = await db.fetch_all(sql, tuple(params))
    return [dict(r) for r in rows]
```

- [ ] **Step 2: Wire into `project_summary`**

In `project_summary`, after the `top_sessions = await _top_sessions(...)` call, add:

```python
    by_skill = await _by_skill(db, start=fs, end=fe, project_id=project_id, model=model)
    by_agent = await _by_agent(db, start=fs, end=fe, project_id=project_id, model=model)
```

And add to the returned dict (e.g. after `"by_model": by_model,`):

```python
        "by_skill": by_skill,
        "by_agent": by_agent,
```

- [ ] **Step 3: Wire into `global_summary`**

In `global_summary`, after its `top_sessions = await _top_sessions(...)` call, add:

```python
    by_skill = await _by_skill(db, start=fs, end=fe, project_id=None, model=model)
    by_agent = await _by_agent(db, start=fs, end=fe, project_id=None, model=model)
```

And add the same two keys to its returned dict.

- [ ] **Step 4: Verify with hand-inserted rows**

Run:

```bash
python -c "import asyncio, tempfile, os, datetime as dt
from dreaming.services.db import SqliteDB
from dreaming.services import ai_usage_stats as s
async def m():
    db = SqliteDB(os.path.join(tempfile.mkdtemp(),'t.db')); await db.connect()
    now = dt.datetime.utcnow().isoformat()
    await db.execute('INSERT INTO projects (slug,label,working_dir,created_at,updated_at) VALUES (?,?,?,?,?)', ('p','P','/w',now,now))
    await db.execute('INSERT INTO ai_usage_events (message_id,project_id,ts,ts_date,session_id,project_slug,source_file,agent_name,input_tokens,output_tokens) VALUES (?,?,?,?,?,?,?,?,?,?)', ('m3',1,'2026-05-27T10:00:00','2026-05-27','sess','p','f.jsonl','Explore',300,30))
    await db.execute('INSERT INTO ai_skill_invocations (message_id,skill_name,project_id,ts,ts_date,session_id,source_file) VALUES (?,?,?,?,?,?,?)', ('m1','brainstorming',1,'2026-05-27T10:00:00','2026-05-27','sess','f.jsonl'))
    sk = await s._by_skill(db, start='2026-05-01', end='2026-05-31', project_id=1)
    ag = await s._by_agent(db, start='2026-05-01', end='2026-05-31', project_id=1)
    assert sk == [{'skill_name':'brainstorming','calls':1,'sessions':1}], sk
    assert ag == [{'agent_name':'Explore','events':1,'runs':1,'total_tokens':330}], ag
    print('OK stats')
    await db.close()
asyncio.run(m())"
```

Expected: `OK stats`

- [ ] **Step 5: Commit**

```bash
git add dreaming/services/ai_usage_stats.py
git commit -m "feat(ai-metrics): _by_skill / _by_agent aggregators + summary keys"
```

---

## Task 3: Parser helpers (pure functions)

**Files:**
- Modify: `dreaming/services/ai_usage_parser.py` (refactor `parse_line`, add `extract_skill_invocations`, add `read_agent_name`).

- [ ] **Step 1: Refactor `parse_line` into `parse_obj` + thin wrapper**

Replace the existing `parse_line` function body so it splits JSON parsing from row building (the ingest loop will parse once and call both `parse_obj` and `extract_skill_invocations`):

```python
def parse_line(
    raw: str,
    *,
    project_slug: str,
    source_file: str,
    source_line: int,
) -> dict[str, Any] | None:
    """Parse a single JSONL line → event row, or None to skip."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parse_obj(
        obj,
        project_slug=project_slug,
        source_file=source_file,
        source_line=source_line,
    )


def parse_obj(
    obj: dict[str, Any],
    *,
    project_slug: str,
    source_file: str,
    source_line: int,
) -> dict[str, Any] | None:
    """Build an event row from an already-parsed JSONL object, or None to skip."""
    t = obj.get("type")
    if t != "assistant":
        return None
    msg = obj.get("message") or {}
    if not isinstance(msg, dict):
        return None

    message_id = msg.get("id")
    if not message_id:
        return None

    usage = msg.get("usage") or {}
    input_t = int(usage.get("input_tokens") or 0)
    output_t = int(usage.get("output_tokens") or 0)
    cache_read_t = int(usage.get("cache_read_input_tokens") or 0)
    cache_creation_t = int(usage.get("cache_creation_input_tokens") or 0)
    if not (input_t or output_t or cache_read_t or cache_creation_t):
        return None

    ts = obj.get("timestamp") or ""
    ts_date = ts[:10] if len(ts) >= 10 else ""
    if not ts_date:
        return None

    return {
        "message_id": message_id,
        "ts": ts,
        "ts_date": ts_date,
        "session_id": obj.get("sessionId") or "",
        "project_slug": project_slug,
        "project_cwd": obj.get("cwd"),
        "git_branch": obj.get("gitBranch"),
        "model": msg.get("model"),
        "is_sidechain": 1 if obj.get("isSidechain") else 0,
        "agent_id": obj.get("agentId"),
        "agent_name": None,
        "input_tokens": input_t,
        "output_tokens": output_t,
        "cache_read_tokens": cache_read_t,
        "cache_creation_tokens": cache_creation_t,
        "source_file": source_file,
        "source_line": source_line,
    }
```

Note the new `"agent_name": None` key — the ingest loop overwrites it for subagent files.

- [ ] **Step 2: Add `extract_skill_invocations`**

Add after `parse_obj`:

```python
def extract_skill_invocations(
    obj: dict[str, Any],
    *,
    source_file: str,
) -> list[dict[str, Any]]:
    """Return one row per distinct `Skill` tool_use block in an assistant message.

    Independent of the usage>0 gate parse_obj applies: skill rows do NOT require
    token usage to be present. `project_id` is attached later by the caller from
    the cwd→project map. Multiple Skill calls in one message are de-duped per
    skill name (the PK is (message_id, skill_name))."""
    if obj.get("type") != "assistant":
        return []
    msg = obj.get("message") or {}
    if not isinstance(msg, dict):
        return []
    message_id = msg.get("id")
    content = msg.get("content")
    if not message_id or not isinstance(content, list):
        return []
    ts = obj.get("timestamp") or ""
    ts_date = ts[:10] if len(ts) >= 10 else ""
    if not ts_date:
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in content:
        if not isinstance(c, dict):
            continue
        if c.get("type") != "tool_use" or c.get("name") != "Skill":
            continue
        inp = c.get("input")
        skill = (inp.get("skill") or "").strip() if isinstance(inp, dict) else ""
        if not skill or skill in seen:
            continue
        seen.add(skill)
        out.append({
            "message_id": message_id,
            "skill_name": skill,
            "ts": ts,
            "ts_date": ts_date,
            "session_id": obj.get("sessionId") or "",
            "is_sidechain": 1 if obj.get("isSidechain") else 0,
            "model": msg.get("model"),
            "source_file": source_file,
        })
    return out
```

- [ ] **Step 3: Add `read_agent_name`**

Add near `discover_jsonl_files` (file-discovery section):

```python
def read_agent_name(jsonl_path: Path) -> str | None:
    """For a subagent file `agent-<hash>.jsonl`, read its sibling
    `agent-<hash>.meta.json` and return the `agentType`, or None."""
    meta = jsonl_path.with_name(jsonl_path.stem + ".meta.json")
    if not meta.exists():
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    name = (data.get("agentType") or "").strip() if isinstance(data, dict) else ""
    return name or None
```

- [ ] **Step 4: Verify the pure functions**

Run:

```bash
python -c "import json
from dreaming.services.ai_usage_parser import extract_skill_invocations, parse_obj
o = {'type':'assistant','timestamp':'2026-05-27T10:00:00Z','sessionId':'s','cwd':'/w','isSidechain':False,'message':{'id':'m1','model':'claude-opus-4-7','usage':{'input_tokens':10,'output_tokens':2},'content':[{'type':'tool_use','name':'Skill','input':{'skill':'brainstorming'}},{'type':'tool_use','name':'Skill','input':{'skill':'brainstorming'}},{'type':'tool_use','name':'Read','input':{}}]}}
sk = extract_skill_invocations(o, source_file='f.jsonl')
assert len(sk)==1 and sk[0]['skill_name']=='brainstorming', sk
row = parse_obj(o, project_slug='p', source_file='f.jsonl', source_line=0)
assert row['agent_name'] is None and row['input_tokens']==10, row
print('OK helpers')"
```

Expected: `OK helpers`

- [ ] **Step 5: Commit**

```bash
git add dreaming/services/ai_usage_parser.py
git commit -m "refactor(ai-metrics): parse_obj split + skill/agent extraction helpers"
```

---

## Task 4: Wire skills + agent_name into the ingest loop

**Files:**
- Modify: `dreaming/services/ai_usage_parser.py` (`_insert_events` column list, new `_insert_skill_invocations`, the per-file loop in `ingest_ai_usage`, result dict).

- [ ] **Step 1: Add `agent_name` to `_insert_events`**

Update the `INSERT OR IGNORE` in `_insert_events` to include `agent_name`:

```python
    await db._conn.executemany(
        "INSERT OR IGNORE INTO ai_usage_events "
        "(message_id, project_id, ts, ts_date, session_id, project_slug, project_cwd, "
        "git_branch, model, is_sidechain, agent_id, agent_name, input_tokens, output_tokens, "
        "cache_read_tokens, cache_creation_tokens, source_file, source_line) "
        "VALUES (:message_id, :project_id, :ts, :ts_date, :session_id, :project_slug, "
        ":project_cwd, :git_branch, :model, :is_sidechain, :agent_id, :agent_name, :input_tokens, "
        ":output_tokens, :cache_read_tokens, :cache_creation_tokens, :source_file, :source_line)",
        [{**r, "project_id": project_id} for r in rows],
    )
```

- [ ] **Step 2: Add `_insert_skill_invocations`**

Add next to `_insert_events`:

```python
async def _insert_skill_invocations(
    db: SqliteDB, project_id: int, rows: list[dict[str, Any]]
) -> int:
    """Batch INSERT OR IGNORE into ai_skill_invocations. Returns inserted count."""
    if not rows or db._conn is None:
        return 0
    before = db._conn.total_changes
    await db._conn.executemany(
        "INSERT OR IGNORE INTO ai_skill_invocations "
        "(message_id, skill_name, project_id, ts, ts_date, session_id, "
        "is_sidechain, model, source_file) "
        "VALUES (:message_id, :skill_name, :project_id, :ts, :ts_date, "
        ":session_id, :is_sidechain, :model, :source_file)",
        [{**r, "project_id": project_id} for r in rows],
    )
    await db._conn.commit()
    return db._conn.total_changes - before
```

- [ ] **Step 3: Rewrite the per-file loop body in `ingest_ai_usage`**

In `ingest_ai_usage`, the loop currently does `for jsonl, is_subagent, slug in files:`. At the top of the loop body (right after `on_disk.add(path_str)`), add the per-file agent name:

```python
            agent_name = read_agent_name(jsonl) if is_subagent else None
```

Then replace the line-parsing block (the `per_project_rows`/`for i, line in enumerate(lines)` section, down to just before `inserted_here = 0`) with:

```python
            # Group rows by resolved project_id; skip those that don't map.
            per_project_rows: dict[int, list[dict[str, Any]]] = {}
            per_project_skills: dict[int, list[dict[str, Any]]] = {}
            errors_in_file = 0
            skipped_rows = 0
            file_project_id = stored["project_id"] if stored else None
            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                try:
                    text = line.decode("utf-8", errors="replace")
                except Exception:
                    errors_in_file += 1
                    continue
                try:
                    obj = json.loads(text)
                except json.JSONDecodeError:
                    if text.strip() and not text.startswith("{"):
                        errors_in_file += 1
                    continue

                # Same pid resolution as before — the original resolved from
                # row["project_cwd"], which parse_obj sets to obj["cwd"]; this is
                # equivalent, just hoisted so skill rows can reuse it.
                cwd = obj.get("cwd")
                pid = cwd_to_pid.get(_norm_for_match(cwd)) if cwd else None

                row = parse_obj(
                    obj, project_slug=slug, source_file=path_str, source_line=i,
                )
                if row is not None:
                    if pid is None:
                        skipped_rows += 1
                    else:
                        row["agent_name"] = agent_name
                        per_project_rows.setdefault(pid, []).append(row)
                        if file_project_id is None:
                            file_project_id = pid

                skill_rows = extract_skill_invocations(obj, source_file=path_str)
                if skill_rows and pid is not None:
                    per_project_skills.setdefault(pid, []).extend(skill_rows)
```

Then, after the existing `for pid, prows in per_project_rows.items():` insert block (which sets `inserted_here`), add skill insertion:

```python
            skills_here = 0
            for pid, srows in per_project_skills.items():
                for start in range(0, len(srows), batch_size):
                    skills_here += await _insert_skill_invocations(
                        db, pid, srows[start:start + batch_size]
                    )
```

And after `result["events_inserted"] += inserted_here` (the success path near the end of the loop), add:

```python
            result["skills_inserted"] += skills_here
```

- [ ] **Step 4: Add `skills_inserted` to the result dict**

In `ingest_ai_usage`, extend the initial `result = {...}`:

```python
    result = {
        "files": 0,
        "events_inserted": 0,
        "skills_inserted": 0,
        "events_skipped": 0,
        "errors": 0,
        "duration_ms": 0,
    }
```

> Note: the `file_pid`-only-matched-nothing early-`continue` path (where the file matched no project) skips the success block — that is correct, since `per_project_skills` is also empty there.

- [ ] **Step 5: Verify imports resolve and module loads**

Run:

```bash
python -c "import dreaming.services.ai_usage_parser as p; print('OK', hasattr(p,'_insert_skill_invocations'))"
```

Expected: `OK True`

- [ ] **Step 6: Commit**

```bash
git add dreaming/services/ai_usage_parser.py
git commit -m "feat(ai-metrics): ingest stamps agent_name + records skill invocations"
```

---

## Task 5: History backfill + startup hook

**Files:**
- Modify: `dreaming/services/ai_usage_parser.py` (add `backfill_skill_agent_stats`).
- Modify: `dreaming/main.py` (kick the backfill once on startup).

- [ ] **Step 1: Add `backfill_skill_agent_stats`**

Add at the end of `ai_usage_parser.py`:

```python
async def backfill_skill_agent_stats(
    db: SqliteDB,
    projects: ProjectsService,
    claude_projects_dir: str | None = None,
    max_files: int = 20000,
) -> dict:
    """One-time re-scan from offset 0 that backfills `agent_name` on existing
    ai_usage_events rows and fills ai_skill_invocations for historical files.

    The incremental ingest tracks byte offsets and skips unchanged files, and
    INSERT OR IGNORE won't update the new column on existing rows — so history
    needs this dedicated pass. Idempotent: the UPDATE is deterministic and skill
    inserts use INSERT OR IGNORE."""
    result = {"files": 0, "agent_files": 0, "skills_inserted": 0, "errors": 0}
    try:
        cwd_to_pid = await build_cwd_to_project_id(db)
        if not cwd_to_pid:
            return result
        root = resolve_claude_projects_root(claude_projects_dir)
        files = list(discover_jsonl_files(root))
        if max_files and len(files) > max_files:
            files = files[:max_files]
        for jsonl, is_subagent, slug in files:
            result["files"] += 1
            path_str = str(jsonl)

            if is_subagent:
                agent_name = read_agent_name(jsonl)
                if agent_name:
                    try:
                        await db.execute(
                            "UPDATE ai_usage_events SET agent_name=? "
                            "WHERE source_file=? AND (agent_name IS NULL OR agent_name='')",
                            (agent_name, path_str),
                        )
                        result["agent_files"] += 1
                    except Exception:
                        result["errors"] += 1

            try:
                per_pid: dict[int, list[dict[str, Any]]] = {}
                with jsonl.open(encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if '"Skill"' not in line:
                            continue
                        try:
                            obj = json.loads(line)
                        except ValueError:
                            continue
                        srows = extract_skill_invocations(obj, source_file=path_str)
                        if not srows:
                            continue
                        cwd = obj.get("cwd")
                        pid = cwd_to_pid.get(_norm_for_match(cwd)) if cwd else None
                        if pid is None:
                            continue
                        per_pid.setdefault(pid, []).extend(srows)
                for pid, srows in per_pid.items():
                    result["skills_inserted"] += await _insert_skill_invocations(
                        db, pid, srows
                    )
            except OSError:
                result["errors"] += 1
    except Exception:
        log.exception("backfill_skill_agent_stats failed")
        result["errors"] += 1
    log.info("backfill_skill_agent_stats: %s", result)
    return result
```

- [ ] **Step 2: Kick the backfill once on startup**

In `dreaming/main.py`, add a module-level logger and import asyncio at the top:

```python
import asyncio
import logging
```
```python
log = logging.getLogger(__name__)
```

Then in `lifespan`, after the per-project job registration loop and before `app.state.resolver_factory = get_resolver`, add:

```python
    # One-time backfill of skill/agent breakdown for pre-existing history.
    # Runs in the background so startup isn't blocked; guarded so it only fires
    # while ai_skill_invocations is still empty. Idempotent if it re-fires.
    try:
        row = await app.state.db.fetch_one(
            "SELECT COUNT(*) AS c FROM ai_skill_invocations"
        )
        has_events = await app.state.db.fetch_one(
            "SELECT 1 FROM ai_usage_events LIMIT 1"
        )
        if row is not None and int(row["c"]) == 0 and has_events is not None:
            from dreaming.services.ai_usage_parser import backfill_skill_agent_stats
            asyncio.create_task(
                backfill_skill_agent_stats(app.state.db, app.state.projects)
            )
    except Exception as e:
        log.warning("skill/agent backfill kickoff failed: %s", e)
```

> Note: if a project genuinely never uses skills, this re-scans (cheaply, thanks to the `'"Skill"'` substring fast-path and the deterministic agent UPDATE) on each startup until at least one skill is recorded. That is acceptable and avoids adding a marker table (YAGNI). The incremental ingest keeps both dimensions current for all new files going forward.

- [ ] **Step 3: Verify module loads**

Run:

```bash
python -c "import dreaming.main; import dreaming.services.ai_usage_parser as p; print('OK', hasattr(p,'backfill_skill_agent_stats'))"
```

Expected: `OK True`

- [ ] **Step 4: Commit**

```bash
git add dreaming/services/ai_usage_parser.py dreaming/main.py
git commit -m "feat(ai-metrics): one-time startup backfill of skill/agent history"
```

---

## Task 6: End-to-end smoke

**Files:**
- Create: `scripts/smoke_skill_agent_stats.py`

- [ ] **Step 1: Write the smoke script** (use the Write tool — contains no Cyrillic, but keep UTF-8)

```python
"""Smoke: skills/agents breakdown — ingest a fixture session tree, verify
agent_name stamping, skill invocation recording, the stats aggregators, and
backfill idempotency. Function-level (no server needed)."""
import asyncio
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services.db import SqliteDB
from dreaming.services.projects import ProjectsService
from dreaming.services.ai_usage_parser import (
    ingest_ai_usage,
    backfill_skill_agent_stats,
)
from dreaming.services import ai_usage_stats as stats


def _line(**kw) -> str:
    return json.dumps(kw)


async def run() -> int:
    tmp = Path(tempfile.mkdtemp())
    workdir = tmp / "proj"
    workdir.mkdir()
    cwd = str(workdir)

    root = tmp / "claude_projects"
    slug_dir = root / "proj-slug"
    slug_dir.mkdir(parents=True)
    sess = "session-uuid-1"

    main = slug_dir / f"{sess}.jsonl"
    main.write_text("\n".join([
        _line(type="assistant", timestamp="2026-05-27T10:00:00Z", sessionId=sess,
              cwd=cwd, isSidechain=False,
              message={"id": "m1", "model": "claude-opus-4-7",
                       "usage": {"input_tokens": 100, "output_tokens": 50},
                       "content": [{"type": "tool_use", "name": "Skill",
                                    "input": {"skill": "brainstorming"}}]}),
        _line(type="assistant", timestamp="2026-05-27T10:01:00Z", sessionId=sess,
              cwd=cwd, isSidechain=False,
              message={"id": "m2", "model": "claude-opus-4-7",
                       "usage": {"input_tokens": 200, "output_tokens": 20},
                       "content": [{"type": "text", "text": "hi"}]}),
    ]) + "\n", encoding="utf-8")

    sub = slug_dir / sess / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-abc.meta.json").write_text(
        json.dumps({"agentType": "Explore", "description": "d"}), encoding="utf-8")
    (sub / "agent-abc.jsonl").write_text(
        _line(type="assistant", timestamp="2026-05-27T10:02:00Z", sessionId=sess,
              cwd=cwd, isSidechain=True,
              message={"id": "m3", "model": "claude-opus-4-7",
                       "usage": {"input_tokens": 300, "output_tokens": 30},
                       "content": [{"type": "text", "text": "sub"}]}) + "\n",
        encoding="utf-8")

    db = SqliteDB(str(tmp / "t.db"))
    await db.connect()
    now = dt.datetime.utcnow().isoformat()
    await db.execute(
        "INSERT INTO projects (slug,label,working_dir,created_at,updated_at) "
        "VALUES (?,?,?,?,?)",
        ("proj-slug", "Proj", cwd, now, now),
    )
    projects = ProjectsService(db)

    res = await ingest_ai_usage(db, projects, claude_projects_dir=str(root))
    print("ingest:", res)
    assert res["skills_inserted"] == 1, res

    sk = await stats._by_skill(db, start="2026-05-01", end="2026-05-31")
    assert any(r["skill_name"] == "brainstorming" and r["calls"] == 1 for r in sk), sk

    ag = await stats._by_agent(db, start="2026-05-01", end="2026-05-31")
    assert any(r["agent_name"] == "Explore" and r["total_tokens"] == 330
               and r["runs"] == 1 for r in ag), ag

    # Summary keys present
    summ = await stats.project_summary(db, 1, preset="all")
    assert "by_skill" in summ and "by_agent" in summ, list(summ)

    # Backfill is idempotent (no new skill rows, agent_name already set)
    bf = await backfill_skill_agent_stats(db, projects, claude_projects_dir=str(root))
    print("backfill:", bf)
    sk2 = await stats._by_skill(db, start="2026-05-01", end="2026-05-31")
    assert sk2 == sk, (sk, sk2)

    print("OK smoke_skill_agent_stats")
    await db.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
```

- [ ] **Step 2: Run the smoke**

Run: `python scripts/smoke_skill_agent_stats.py`
Expected (final line): `OK smoke_skill_agent_stats`

If `ingest` shows `skills_inserted: 0`, re-check Task 4 Step 3 (the `extract_skill_invocations` call and `per_project_skills` insertion). If `_by_agent` is empty, re-check `read_agent_name` and the `row["agent_name"] = agent_name` assignment.

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_skill_agent_stats.py
git commit -m "test(ai-metrics): smoke for skill/agent ingest + stats + backfill"
```

---

## Task 7: UI sections + i18n

**Files:**
- Modify: `dreaming/i18n/messages_ru.json`, `dreaming/i18n/messages_en.json`
- Modify: `dreaming/templates/project_ai_usage.html`, `dreaming/templates/global_ai_usage.html`

- [ ] **Step 1: Add RU i18n keys** (Write/Edit tool only — UTF-8)

In `dreaming/i18n/messages_ru.json`, after the `"ai_usage.main_vs_sub"` line, add:

```json
  "ai_usage.by_skill": "По скилам (вызовы)",
  "ai_usage.by_agent": "По агентам (токены)",
  "ai_usage.col.calls": "Вызовы",
  "ai_usage.col.runs": "Запуски",
  "ai_usage.col.skill": "Скил",
  "ai_usage.col.agent": "Агент",
```

- [ ] **Step 2: Add EN i18n keys (mirror)** in `dreaming/i18n/messages_en.json`, in the matching location:

```json
  "ai_usage.by_skill": "By skill (calls)",
  "ai_usage.by_agent": "By agent (tokens)",
  "ai_usage.col.calls": "Calls",
  "ai_usage.col.runs": "Runs",
  "ai_usage.col.skill": "Skill",
  "ai_usage.col.agent": "Agent",
```

- [ ] **Step 3: Verify i18n parity**

Run: `python scripts/check_i18n.py`
Expected: success / no missing-key errors.

- [ ] **Step 4: Add the new section to both templates**

In **both** `project_ai_usage.html` and `global_ai_usage.html`, insert this block immediately after the `</div>` that closes the "models / sidechain" `grid ... lg:grid-cols-3` row. The marker comment differs between the files:
- In `project_ai_usage.html` the grid closes at ~line 108; insert the new block right **before** `{# 5. Top sessions #}` (~line 110).
- In `global_ai_usage.html` there is **no** `{# 5. Top sessions #}` comment — the same grid closes at ~line 110; insert the new block right **before** `{# Top projects table … #}` (~line 112).

```html
{# 3b. Skills (calls) / Agents (tokens) breakdown #}
<div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
  <div class="rounded-xl p-5" style="background: var(--bg-card); border:1px solid var(--border-subtle);">
    <h2 class="text-sm font-semibold mb-4" style="color: var(--text-strong);">{{ "ai_usage.by_skill" | t(locale=locale) }}</h2>
    {% if summary.by_skill %}
    <div style="height: 16rem;"><canvas id="skillChart"></canvas></div>
    {% else %}
    <p class="text-sm" style="color: var(--text-faint);">{{ "common.no_data" | t(locale=locale) }}</p>
    {% endif %}
  </div>
  <div class="rounded-xl p-5" style="background: var(--bg-card); border:1px solid var(--border-subtle);">
    <h2 class="text-sm font-semibold mb-4" style="color: var(--text-strong);">{{ "ai_usage.by_agent" | t(locale=locale) }}</h2>
    {% if summary.by_agent %}
    <table class="w-full text-sm">
      <thead class="text-xs uppercase tracking-wider" style="color: var(--text-faint);">
        <tr>
          <th class="text-left pb-2">{{ "ai_usage.col.agent" | t(locale=locale) }}</th>
          <th class="text-right pb-2">{{ "ai_usage.col.runs" | t(locale=locale) }}</th>
          <th class="text-right pb-2">{{ "ai_usage.col.tokens" | t(locale=locale) }}</th>
        </tr>
      </thead>
      <tbody>
        {% for a in summary.by_agent %}
        <tr style="border-top:1px solid var(--border-subtle);">
          <td class="py-2" style="color: var(--text-body);">{{ a.agent_name }}</td>
          <td class="py-2 text-right" style="color: var(--text-faint);">{{ a.runs }}</td>
          <td class="py-2 text-right font-semibold" style="color: var(--text-strong);">{{ num(a.total_tokens) }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <p class="text-sm" style="color: var(--text-faint);">{{ "common.no_data" | t(locale=locale) }}</p>
    {% endif %}
  </div>
</div>
```

- [ ] **Step 5: Add the skills bar chart to both templates' `<script>` blocks**

In **both** files, inside the existing `(() => { ... })();` IIFE, after the `const byModel = ...` line add:

```javascript
  const bySkill = {{ (summary.by_skill or []) | tojson }};
```

And before the closing `})();`, add:

```javascript
  // Skills horizontal bar (calls)
  if (bySkill.length) {
    const top = bySkill.slice(0, 12);
    new Chart(document.getElementById('skillChart'), {
      type: 'bar',
      data: {
        labels: top.map(s => s.skill_name),
        datasets: [{ label: 'Calls', data: top.map(s => s.calls), backgroundColor: '#a78bfa' }],
      },
      options: {
        indexAxis: 'y',
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { backgroundColor: '#111827', borderColor: '#1e293b', borderWidth: 1, padding: 8 },
        },
        scales: {
          x: { ticks: { font: { size: 11 }, precision: 0 }, grid: { color: 'rgba(255,255,255,0.04)' } },
          y: { ticks: { font: { size: 11 } }, grid: { display: false } },
        },
      },
    });
  }
```

- [ ] **Step 6: Verify in the running app**

Start the server: `python -m uvicorn dreaming.main:app --port 8086 --reload`
Visit `http://localhost:8086/ai-usage` and a project page `http://localhost:8086/p/<slug>/ai-usage`.
Expected: a new two-card row "По скилам (вызовы)" / "По агентам (токены)" renders below "Main vs Subagents"; the skills bar shows skill names with call counts; the agents table lists agentType · runs · tokens. With no data yet, both show the "no data" placeholder (the startup backfill populates history within a few seconds — refresh).

- [ ] **Step 7: Commit**

```bash
git add dreaming/i18n/messages_ru.json dreaming/i18n/messages_en.json dreaming/templates/project_ai_usage.html dreaming/templates/global_ai_usage.html
git commit -m "feat(ai-metrics): skills/agents breakdown UI section (project + global)"
```

---

## Done criteria

- `python scripts/smoke_skill_agent_stats.py` prints `OK smoke_skill_agent_stats`.
- `python scripts/check_i18n.py` passes.
- Both `/ai-usage` and `/p/<slug>/ai-usage` render the new section with real data after the startup backfill.
- New code follows existing patterns; no pytest added (repo convention).
