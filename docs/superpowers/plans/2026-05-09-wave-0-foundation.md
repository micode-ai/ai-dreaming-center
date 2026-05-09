# AI Dreaming Center — Wave 0 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap `ai-dreaming-center` to the point where: (a) repo is initialized, (b) FastAPI server boots on port 8086, (c) `/setup` wizard scans `d:\Work\micode\` and imports projects into a SQLite registry, (d) `/projects` lists them, (e) project resolver middleware enforces `/p/{slug}/` (404 on unknown slug), (f) i18n infrastructure with Jinja `t()` filter is wired, (g) global `/settings` reads/writes `config.yaml`, (h) all later-wave service files exist as no-op stubs so downstream wave plans don't need to scaffold them.

**Architecture:** Fork ALC's structure under a renamed `dreaming/` package; keep ALC's patterns (lifespan singletons, aiosqlite, Jinja2+htmx+Tailwind CDN, APScheduler, Pydantic-settings). New: `projects` and `project_settings` tables in DB, project resolver middleware, KV-style override config, i18n loader with CLDR plural rules. Database is greenfield (no migration from ALC). Wave 0 produces a server that boots, imports projects, but has no domain features yet — those land in Waves 1-5.

**Tech Stack:** Python 3.10+, FastAPI, Uvicorn, Jinja2, aiosqlite, sse-starlette, APScheduler, pydantic-settings, pyyaml, tzlocal, markdown, psutil. No test framework (per ALC convention; smoke tests in `docs/smoke-tests.md`).

**Spec reference:** `D:\Work\RsCloud2022\agent-learning-center\docs\superpowers\specs\2026-05-09-ai-dreaming-center-design.md`

**Working directory for ALL tasks below:** `D:\Work\micode\ai-dreaming-center\` (currently empty).

**Source for copy-and-adapt:** `D:\Work\RsCloud2022\agent-learning-center\app\` (ALC).

## Executor environment notes (read first)

- **Shell.** User environment is Windows 11 + PowerShell. Smoke commands shown below use bash idioms (`rm -f`, `&`, `sleep`, `$(...)`, `grep`). Run them via the Bash tool, which is available in this environment, OR translate to PowerShell. The Bash tool resolves to Git-Bash on Windows; absolute Windows paths (`D:\Work\...`) work; backslashes need to be escaped or paths quoted.
- **Virtualenv.** Every Python install step assumes an active venv (`.venv` at the project root). Task 3 creates and activates it. If the environment forbids global pip (PEP 668), the venv is mandatory.
- **File creation.** Use the Write/Edit tool for all source/template/JSON files — it writes UTF-8. Avoid PowerShell `Set-Content`/`Out-File` for files containing Cyrillic (defaults to UTF-16 LE with BOM and breaks JSON parsing).
- **Multi-line `python -c "..."`** does not survive shell quoting on Windows. The plan uses standalone files under `scripts/` for any Python smoke check beyond a single line.

---

## File Structure (created in Wave 0)

```
ai-dreaming-center/
├── .gitignore
├── README.md
├── CLAUDE.md
├── pyproject.toml
├── config.example.yaml
├── data/                          # gitignored, populated at runtime
├── docs/
│   ├── smoke-tests.md
│   ├── superpowers/
│   │   ├── specs/
│   │   │   └── 2026-05-09-ai-dreaming-center-design.md   (copied from ALC)
│   │   └── plans/
│   │       └── 2026-05-09-wave-0-foundation.md           (this plan)
├── dreaming/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── i18n/
│   │   ├── __init__.py
│   │   ├── messages_ru.json
│   │   └── messages_en.json
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── project_resolver.py
│   │   └── setup_gate.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── root.py
│   │   ├── setup.py
│   │   ├── projects.py
│   │   └── settings.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── db.py
│   │   ├── projects.py
│   │   ├── config_resolver.py
│   │   ├── i18n.py
│   │   ├── process_manager.py          (stub — public API only)
│   │   ├── orchestration_hub.py        (stub)
│   │   ├── claude_session_tail.py      (stub)
│   │   ├── subagent_watcher.py         (stub)
│   │   ├── subagent_backfill.py        (stub)
│   │   └── scheduler.py                (Wave 0 minimal: registers reconcile_stale_sessions only)
│   ├── templates/
│   │   ├── base.html
│   │   ├── _navbar.html                (project selector, locale toggle, scheduler pause placeholder)
│   │   ├── index_placeholder.html      (Wave 0 root /)
│   │   ├── setup.html                  (multi-step wizard)
│   │   ├── projects.html               (list/CRUD)
│   │   └── settings.html               (global)
│   └── static/
│       └── app.css
└── scripts/
    └── check_i18n.py                   (key-parity verifier)
```

**Stubs in Wave 0:** `process_manager.py`, `orchestration_hub.py`, `claude_session_tail.py`, `subagent_watcher.py`, `subagent_backfill.py` are created with the public API of their ALC counterparts but no-op bodies, so Wave 1+ imports work without rebuilding the package layout.

---

## Sub-skills referenced
- `@superpowers:verification-before-completion` — before claiming each task done, run the listed verify command and confirm output.
- `@superpowers:subagent-driven-development` — recommended way to execute this plan task-by-task.

---

## Phase 0.1 — Project skeleton & first boot

### Task 1: Initialize repo and base files

**Files:**
- Create: `D:\Work\micode\ai-dreaming-center\.gitignore`
- Create: `D:\Work\micode\ai-dreaming-center\pyproject.toml`
- Create: `D:\Work\micode\ai-dreaming-center\config.example.yaml`
- Create: `D:\Work\micode\ai-dreaming-center\README.md` (one-line placeholder, polished in Wave 5)
- Create: `D:\Work\micode\ai-dreaming-center\CLAUDE.md` (one-line placeholder, polished in Wave 5)

- [ ] **Step 1: Create `.gitignore`**

```
__pycache__/
*.pyc
*.egg-info/
.venv/
venv/
data/
config.yaml
.idea/
.vscode/
*.db
*.db-shm
*.db-wal
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "ai-dreaming-center"
version = "0.1.0"
description = "Multi-project orchestration dashboard for Claude CLI agent teams"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "jinja2>=3.1",
    "aiosqlite>=0.20",
    "sse-starlette>=2.2",
    "apscheduler>=3.10",
    "pydantic-settings>=2.7",
    "pyyaml>=6.0",
    "tzlocal>=5.0",
    "markdown>=3.6",
    "psutil>=5.9",
]

[project.scripts]
dreaming = "uvicorn:main"

[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["dreaming*"]
```

- [ ] **Step 3: Create `config.example.yaml`** (global defaults only; per-project overrides go in DB)

Copy `config.example.yaml` from ALC verbatim, then replace these lines:
- Remove: `working_dir: ...` (now per-project)
- Add: `projects_root: "D:\\Work\\micode"` (after `claude_path:`)
- Replace: `port: 8085` → `port: 8086`
- Add: `default_locale: "ru"` (after `port:`)

- [ ] **Step 4: Create placeholder `README.md`**

```markdown
# AI Dreaming Center

Multi-project FastAPI dashboard for Claude CLI agent orchestration. Fork of [agent-learning-center](https://github.com/RsCloud2022/agent-learning-center) extended with multi-project support.

(Full README populated in Wave 5.)
```

- [ ] **Step 5: Create placeholder `CLAUDE.md`**

```markdown
# CLAUDE.md

(Full architecture guide populated in Wave 5. See `docs/superpowers/specs/2026-05-09-ai-dreaming-center-design.md` for the design spec until then.)
```

- [ ] **Step 6: Initialize git and first commit**

```bash
cd /d/Work/micode/ai-dreaming-center
git init
git add .gitignore pyproject.toml config.example.yaml README.md CLAUDE.md
git commit -m "chore: project skeleton"
```

Verify: `git log --oneline` shows one commit.

---

### Task 2: Copy spec & plans into the new repo

**Files:**
- Create: `D:\Work\micode\ai-dreaming-center\docs\superpowers\specs\2026-05-09-ai-dreaming-center-design.md`
- Create: `D:\Work\micode\ai-dreaming-center\docs\superpowers\plans\2026-05-09-wave-0-foundation.md`
- Create: `D:\Work\micode\ai-dreaming-center\docs\smoke-tests.md`

- [ ] **Step 1: Copy spec from ALC**

```bash
mkdir -p docs/superpowers/specs docs/superpowers/plans
cp /d/Work/RsCloud2022/agent-learning-center/docs/superpowers/specs/2026-05-09-ai-dreaming-center-design.md docs/superpowers/specs/
cp /d/Work/RsCloud2022/agent-learning-center/docs/superpowers/plans/2026-05-09-ai-dreaming-center-wave-0-foundation.md docs/superpowers/plans/2026-05-09-wave-0-foundation.md
```

- [ ] **Step 2: Stub smoke-tests.md**

```markdown
# Smoke Tests

Manual verification scripts. Run after each wave's acceptance criteria are claimed met.

## Wave 0 — Foundation
1. Server boots: `python -m uvicorn dreaming.main:app --port 8086` returns no traceback; `curl localhost:8086/health` → `{"ok": true}`.
2. Empty-DB redirect: visit `http://localhost:8086/` → 303 to `/setup`.
3. Setup wizard: at `/setup`, scanner shows 11 directories under `d:\Work\micode\`. Submitting all checked → DB has 11 rows in `projects`.
4. `/projects` lists 11 entries.
5. `/p/UNKNOWN/` → 404 with "project not found".
6. i18n: switching `dc_locale` cookie to `en` changes navbar labels (verify after messages_en.json populated).

(Waves 1-5 add their own sections.)
```

- [ ] **Step 3: Commit**

```bash
git add docs/
git commit -m "docs: copy spec, init plan and smoke-tests"
```

---

### Task 3: Minimal FastAPI app that boots

**Files:**
- Create: `dreaming/__init__.py` (empty)
- Create: `dreaming/main.py`
- Create: `dreaming/config.py`

- [ ] **Step 1: Create `dreaming/__init__.py`**

Empty file.

- [ ] **Step 2: Create `dreaming/config.py` (minimal AppSettings)**

```python
"""Global config — Pydantic-settings + config.yaml + DC_* env vars."""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


CONFIG_PATH = Path("config.yaml")


def _load_yaml() -> dict:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DC_", extra="ignore")

    # Database
    db_path: str = "data/dreaming.db"

    # Projects
    projects_root: str = ""
    default_locale: str = "ru"

    # Server
    host: str = "0.0.0.0"
    port: int = 8086

    # Claude CLI (defaults; overridable per-project)
    claude_path: str = "claude"

    @classmethod
    def load(cls) -> "AppSettings":
        return cls(**_load_yaml())


def settings() -> AppSettings:
    return AppSettings.load()
```

- [ ] **Step 3: Create `dreaming/main.py` (skeleton)**

```python
"""ai-dreaming-center FastAPI entry point."""
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from dreaming.config import settings as load_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = load_settings()
    yield


app = FastAPI(title="AI Dreaming Center", lifespan=lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})
```

- [ ] **Step 4: Create and activate virtualenv, then install**

```bash
python -m venv .venv
# bash:
source .venv/Scripts/activate
# OR PowerShell:
# .\.venv\Scripts\Activate.ps1
pip install -e .
```

Verify: `pip show ai-dreaming-center` shows the package and the path resolves under `.venv/`.

- [ ] **Step 5: Boot the server**

```bash
python -m uvicorn dreaming.main:app --port 8086
```

In another shell:

```bash
curl http://localhost:8086/health
```

Expected: `{"ok":true}`. Stop the server with Ctrl+C.

- [ ] **Step 6: Commit**

```bash
git add dreaming/__init__.py dreaming/main.py dreaming/config.py
git commit -m "feat: minimal FastAPI app boots on 8086 with /health"
```

---

## Phase 0.2 — Database layer

### Task 4: SQLite schema — fork ALC verbatim + insert `project_id`

**Files:**
- Create: `dreaming/services/__init__.py` (empty)
- Create: `dreaming/services/db.py`
- Modify: `dreaming/main.py` (add db wiring in lifespan)

**Approach.** ALC's `_SCHEMA` (in `D:\Work\RsCloud2022\agent-learning-center\app\services\db.py:29-209`) is the source of truth for column lists, types, NOT-NULL, indices, dedup constraints. Every existing dreaming-center table copies that file's column list **exactly**, with only the following mechanical inserts:

1. New `projects` and `project_settings` tables (added at top of `_SCHEMA`).
2. Each ALC table gets a `project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE` column inserted right after the original PK column. Exception: `agent_learning_rotation` PK is rebuilt as `(project_id, agent_name)`; `ai_usage_files` PK is rebuilt as `(project_id, path)`.
3. New per-project indices added (table below).
4. PRAGMAs (`journal_mode=WAL`, `foreign_keys=ON`) execute SEPARATELY from `executescript` (PRAGMA journal_mode is no-op inside a transaction).
5. Connection: persistent `aiosqlite.Connection` on `SqliteDB` (matches ALC's `_conn` pattern in `app/services/db.py:217`). Per-call connections defeat WAL mode and are ~30× slower for typical render fan-out.

**Per-project indices to add** (one per denorm table + per-project base table):

| Table | New index |
|------|-----------|
| `agent_learning_sessions` | `(project_id, started_at DESC)` |
| `custom_topics` | `(project_id, active)` |
| `orchestrator_runs` | `(project_id, started_at DESC)` |
| `orchestrator_nodes` | `(project_id, run_id)` |
| `orchestrator_messages` | `(project_id, node_id, ts DESC)` |
| `orchestrator_questions` | `(project_id, run_id, status)` |
| `orchestrator_tts_messages` | `(project_id, ts DESC)` |
| `ai_usage_events` | `(project_id, ts_date)` |

ALC's existing indices stay as-is.

**`_migrate_orchestration` parity.** Wave 0 is greenfield, but `db.py` retains an idempotent `_migrate_orchestration()` so future schema bumps (e.g. dedup_hash, stage_id, orchestrator_questions) follow the same pattern. Copy ALC's `_migrate_orchestration` body verbatim, with these additions:
- `orchestrator_questions` schema gets `project_id INTEGER NOT NULL` column inline.
- After every `ALTER TABLE` migrating an existing column, no `project_id` migration is needed (greenfield only).

- [ ] **Step 1: Create `dreaming/services/__init__.py`** (empty)

- [ ] **Step 2a: Compose `_SCHEMA` constant by forking ALC verbatim**

Open `D:\Work\RsCloud2022\agent-learning-center\app\services\db.py` (lines 29-209) — that text is the baseline. Produce `dreaming/services/db.py` with the schema below. Differences vs ALC are marked `-- + dreaming` in comments; everything else is byte-identical to ALC.

```python
"""SQLite async client for ai-dreaming-center.

Greenfield schema: forks ALC's _SCHEMA verbatim; injects project_id where the
spec requires; new projects + project_settings registries on top.
"""
from __future__ import annotations
import json
import logging
import uuid
from pathlib import Path
from typing import Any
import aiosqlite

log = logging.getLogger(__name__)


_SCHEMA = """
-- + dreaming: project registry
CREATE TABLE IF NOT EXISTS projects (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    slug         TEXT UNIQUE NOT NULL,
    label        TEXT NOT NULL,
    working_dir  TEXT NOT NULL,
    enabled      INTEGER NOT NULL DEFAULT 1,
    is_default   INTEGER NOT NULL DEFAULT 0,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    color        TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_enabled ON projects(enabled, sort_order);

-- + dreaming: KV overrides per project
CREATE TABLE IF NOT EXISTS project_settings (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    PRIMARY KEY (project_id, key)
);

-- == ALC tables (verbatim columns) + project_id ============================

CREATE TABLE IF NOT EXISTS agent_learning_sessions (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,  -- + dreaming
    agent_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT,
    tokens_total INTEGER,
    model TEXT,
    topic TEXT,
    note_path TEXT,
    error_message TEXT,
    entity_page TEXT,
    confidence REAL
);
CREATE INDEX IF NOT EXISTS idx_als_agent ON agent_learning_sessions (agent_name);
CREATE INDEX IF NOT EXISTS idx_als_started ON agent_learning_sessions (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_als_project_started
    ON agent_learning_sessions (project_id, started_at DESC);  -- + dreaming

-- + dreaming: PK rebuilt as (project_id, agent_name)
CREATE TABLE IF NOT EXISTS agent_learning_rotation (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    tier INTEGER DEFAULT 2,
    last_studied_at TEXT,
    enabled INTEGER DEFAULT 1,
    PRIMARY KEY (project_id, agent_name)
);

CREATE TABLE IF NOT EXISTS custom_topics (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,  -- + dreaming
    title TEXT NOT NULL,
    module TEXT DEFAULT '',
    target_agents TEXT DEFAULT '',
    question TEXT DEFAULT '',
    why_important TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    active INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_topics_project_active
    ON custom_topics (project_id, active);  -- + dreaming

CREATE TABLE IF NOT EXISTS orchestrator_runs (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,  -- + dreaming
    external_id TEXT,
    goal TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_or_runs_started ON orchestrator_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_or_runs_project_started
    ON orchestrator_runs (project_id, started_at DESC);  -- + dreaming

CREATE TABLE IF NOT EXISTS orchestrator_nodes (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,  -- + dreaming (denorm)
    run_id TEXT NOT NULL,
    external_id TEXT,
    parent_node_id TEXT,
    agent_name TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    current_action TEXT,
    progress REAL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    last_heartbeat_at TEXT,
    FOREIGN KEY(run_id) REFERENCES orchestrator_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_or_nodes_run ON orchestrator_nodes (run_id);
CREATE INDEX IF NOT EXISTS idx_or_nodes_parent ON orchestrator_nodes (parent_node_id);
CREATE INDEX IF NOT EXISTS idx_or_nodes_project_run
    ON orchestrator_nodes (project_id, run_id);  -- + dreaming

CREATE TABLE IF NOT EXISTS orchestrator_messages (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,  -- + dreaming (denorm)
    run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    author TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    delivery_status TEXT,
    client_message_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_or_msg_node_ts ON orchestrator_messages (node_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_or_msg_project_node_ts
    ON orchestrator_messages (project_id, node_id, ts DESC);  -- + dreaming

-- NOT denormalized: project reached via JOIN to orchestrator_runs
CREATE TABLE IF NOT EXISTS orchestrator_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_or_evt_run_ts ON orchestrator_events (run_id, ts DESC);

-- NOT denormalized
CREATE TABLE IF NOT EXISTS orchestrator_stages (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage_index INTEGER NOT NULL,
    stage_key TEXT NOT NULL,
    label TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    iteration INTEGER NOT NULL DEFAULT 1,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY(run_id) REFERENCES orchestrator_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_or_stages_run ON orchestrator_stages (run_id, stage_index);

-- NOT denormalized
CREATE TABLE IF NOT EXISTS orchestrator_gate_verdicts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    returned_to_stage_id TEXT,
    iteration INTEGER NOT NULL DEFAULT 1,
    comment TEXT,
    decided_by_node_id TEXT,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_or_verdicts_run ON orchestrator_gate_verdicts (run_id, ts DESC);

-- NOT denormalized
CREATE TABLE IF NOT EXISTS orchestrator_artifacts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage_id TEXT,
    node_id TEXT,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    content_preview TEXT,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_or_artifacts_run ON orchestrator_artifacts (run_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_or_artifacts_stage ON orchestrator_artifacts (stage_id);

CREATE TABLE IF NOT EXISTS ai_usage_events (
    message_id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,  -- + dreaming
    ts TEXT NOT NULL,
    ts_date TEXT NOT NULL,
    session_id TEXT NOT NULL,
    project_slug TEXT NOT NULL,
    project_cwd TEXT,
    git_branch TEXT,
    model TEXT,
    is_sidechain INTEGER NOT NULL DEFAULT 0,
    agent_id TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    source_file TEXT NOT NULL,
    source_line INTEGER
);
CREATE INDEX IF NOT EXISTS idx_aue_ts_date   ON ai_usage_events (ts_date);
CREATE INDEX IF NOT EXISTS idx_aue_project   ON ai_usage_events (project_slug, ts_date);
CREATE INDEX IF NOT EXISTS idx_aue_model     ON ai_usage_events (model, ts_date);
CREATE INDEX IF NOT EXISTS idx_aue_session   ON ai_usage_events (session_id);
CREATE INDEX IF NOT EXISTS idx_aue_sidechain ON ai_usage_events (is_sidechain, ts_date);
CREATE INDEX IF NOT EXISTS idx_aue_dreaming_project_ts
    ON ai_usage_events (project_id, ts_date);  -- + dreaming

-- + dreaming: PK rebuilt as (project_id, path); rest of columns verbatim
CREATE TABLE IF NOT EXISTS ai_usage_files (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    project_slug TEXT NOT NULL,
    is_subagent INTEGER NOT NULL DEFAULT 0,
    byte_offset INTEGER NOT NULL DEFAULT 0,
    file_size INTEGER NOT NULL DEFAULT 0,
    mtime REAL NOT NULL DEFAULT 0,
    lines_parsed INTEGER NOT NULL DEFAULT 0,
    events_inserted INTEGER NOT NULL DEFAULT 0,
    parse_errors INTEGER NOT NULL DEFAULT 0,
    is_missing INTEGER NOT NULL DEFAULT 0,
    last_scanned_at TEXT,
    PRIMARY KEY (project_id, path)
);
CREATE INDEX IF NOT EXISTS idx_auf_project ON ai_usage_files (project_slug);

CREATE TABLE IF NOT EXISTS orchestrator_tts_messages (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,  -- + dreaming
    run_id TEXT NOT NULL,
    node_id TEXT,
    agent_name TEXT,
    channel TEXT NOT NULL,
    text TEXT NOT NULL,
    ts TEXT NOT NULL,
    dedup_hash TEXT NOT NULL UNIQUE,
    cleared INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(run_id) REFERENCES orchestrator_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_or_tts_run_ts ON orchestrator_tts_messages (run_id, ts);
CREATE INDEX IF NOT EXISTS idx_or_tts_project_ts
    ON orchestrator_tts_messages (project_id, ts DESC);  -- + dreaming
"""
```

- [ ] **Step 2b: Add `_migrate_orchestration` body** — copy ALC's lines 230-282 verbatim into a method on `SqliteDB`, then add `project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE` to the `orchestrator_questions` CREATE statement. Body:

```python
async def _migrate_orchestration(self) -> None:
    """Idempotent migrations for orchestration extensions (stage_id on nodes,
    artifact dedup, orchestrator_questions table). Greenfield-safe."""
    async with self._conn.execute("PRAGMA table_info(orchestrator_nodes)") as cur:
        cols = {row[1] for row in await cur.fetchall()}
    if "stage_id" not in cols:
        try:
            await self._conn.execute("ALTER TABLE orchestrator_nodes ADD COLUMN stage_id TEXT")
        except Exception as e:
            log.warning("Failed to add stage_id column: %s", e)

    async with self._conn.execute("PRAGMA table_info(orchestrator_artifacts)") as cur:
        art_cols = {row[1] for row in await cur.fetchall()}
    if "dedup_hash" not in art_cols:
        try:
            await self._conn.execute("ALTER TABLE orchestrator_artifacts ADD COLUMN dedup_hash TEXT")
        except Exception as e:
            log.warning("Failed to add dedup_hash column: %s", e)
    try:
        await self._conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_or_artifacts_dedup "
            "ON orchestrator_artifacts (run_id, dedup_hash) WHERE dedup_hash IS NOT NULL"
        )
        await self._conn.commit()
    except Exception as e:
        log.warning("Failed to create idx_or_artifacts_dedup: %s", e)

    try:
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orchestrator_questions (
                id TEXT PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                tool_use_id TEXT NOT NULL UNIQUE,
                questions_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                asked_at TEXT NOT NULL,
                answered_at TEXT,
                answer_text TEXT,
                tts_reminded_at TEXT
            )
            """
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_questions_run ON orchestrator_questions(run_id, status)"
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_questions_pending "
            "ON orchestrator_questions(status, asked_at)"
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_questions_project_run_status "
            "ON orchestrator_questions(project_id, run_id, status)"
        )
        await self._conn.commit()
    except Exception as e:
        log.warning("Failed to create orchestrator_questions table: %s", e)
```

**Note for Wave 1+ implementer.** Wave 0's `SqliteDB` exposes only generic helpers (`execute`, `fetch_one`, `fetch_all`). ALC's actual `db.py` has ~50 domain-specific methods (`finish_session`, `set_agent_tier`, `create_orchestration_run`, `append_orchestration_message`, `insert_ai_usage_events`, `reconcile_stale_sessions`, etc.). They are intentionally omitted in Wave 0 because no Wave 0 route uses them. Wave 1+ ports of ALC routes will port the matching helpers in lockstep.

- [ ] **Step 2c: Add `SqliteDB` class with persistent connection (matches ALC's pattern)**

```python
class SqliteDB:
    """Async SQLite wrapper with a single persistent connection (WAL mode)."""

    def __init__(self, path: str):
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        # PRAGMAs MUST run outside of executescript (which wraps statements in
        # a transaction; PRAGMA journal_mode is a no-op inside a transaction).
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._conn.executescript(_SCHEMA)
        await self._migrate_orchestration()
        await self._conn.commit()
        log.info("SQLite connected: %s", self._path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: tuple = ()) -> None:
        await self._conn.execute(sql, params)
        await self._conn.commit()

    async def fetch_one(self, sql: str, params: tuple = ()):
        async with self._conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def fetch_all(self, sql: str, params: tuple = ()) -> list:
        async with self._conn.execute(sql, params) as cur:
            return list(await cur.fetchall())
```

- [ ] **Step 3: Wire DB into lifespan**

Update `dreaming/main.py`:

```python
# add at top of imports
from dreaming.services.db import SqliteDB

# replace lifespan body:
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = load_settings()
    app.state.db = SqliteDB(app.state.settings.db_path)
    await app.state.db.connect()
    try:
        yield
    finally:
        await app.state.db.close()
```

- [ ] **Step 4: Verify DB creates clean**

Run via the Bash tool:

```bash
rm -f data/dreaming.db
python -m uvicorn dreaming.main:app --port 8086 &
SERVER_PID=$!
sleep 3
sqlite3 data/dreaming.db ".tables"
kill $SERVER_PID 2>/dev/null
```

Expected output (16 tables, sorted alphabetically; `orchestrator_questions` is created by `_migrate_orchestration`):

```
agent_learning_rotation     orchestrator_messages
agent_learning_sessions     orchestrator_nodes
ai_usage_events             orchestrator_questions
ai_usage_files              orchestrator_runs
custom_topics               orchestrator_stages
orchestrator_artifacts      orchestrator_tts_messages
orchestrator_events         project_settings
orchestrator_gate_verdicts  projects
```

Also verify journal mode and a column to make sure the schema actually applied:

```bash
sqlite3 data/dreaming.db "PRAGMA journal_mode;"   # → wal
sqlite3 data/dreaming.db "PRAGMA table_info(agent_learning_sessions);" | grep -c project_id   # → 1
sqlite3 data/dreaming.db "PRAGMA table_info(orchestrator_questions);" | grep -c project_id   # → 1
```

- [ ] **Step 5: Commit**

```bash
git add dreaming/services/__init__.py dreaming/services/db.py dreaming/main.py
git commit -m "feat: SQLite schema — fork ALC verbatim + project_id (greenfield)"
```

---

## Phase 0.3 — Project services

### Task 5: `services/projects.py` — CRUD over `projects` and `project_settings`

**Files:**
- Create: `dreaming/services/projects.py`
- Modify: `dreaming/main.py` — register service in lifespan

- [ ] **Step 1: Create `dreaming/services/projects.py`**

```python
"""Projects registry service: CRUD + filesystem scan."""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dreaming.services.db import SqliteDB


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Project:
    id: int
    slug: str
    label: str
    working_dir: str
    enabled: bool
    is_default: bool
    sort_order: int
    color: Optional[str]
    created_at: str
    updated_at: str


def _row_to_project(row) -> Project:
    return Project(
        id=row["id"],
        slug=row["slug"],
        label=row["label"],
        working_dir=row["working_dir"],
        enabled=bool(row["enabled"]),
        is_default=bool(row["is_default"]),
        sort_order=row["sort_order"],
        color=row["color"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ProjectsService:
    def __init__(self, db: SqliteDB):
        self.db = db

    async def list_all(self, only_enabled: bool = False) -> list[Project]:
        sql = "SELECT * FROM projects"
        if only_enabled:
            sql += " WHERE enabled=1"
        sql += " ORDER BY sort_order, slug"
        rows = await self.db.fetch_all(sql)
        return [_row_to_project(r) for r in rows]

    async def get_by_slug(self, slug: str) -> Optional[Project]:
        row = await self.db.fetch_one("SELECT * FROM projects WHERE slug=?", (slug,))
        return _row_to_project(row) if row else None

    async def get_by_id(self, project_id: int) -> Optional[Project]:
        row = await self.db.fetch_one("SELECT * FROM projects WHERE id=?", (project_id,))
        return _row_to_project(row) if row else None

    async def get_default(self) -> Optional[Project]:
        row = await self.db.fetch_one(
            "SELECT * FROM projects WHERE is_default=1 AND enabled=1 LIMIT 1")
        return _row_to_project(row) if row else None

    async def create(
        self, slug: str, label: str, working_dir: str,
        enabled: bool = True, is_default: bool = False,
        sort_order: int = 0, color: Optional[str] = None,
    ) -> Project:
        ts = _now()
        await self.db.execute(
            """INSERT INTO projects
               (slug, label, working_dir, enabled, is_default, sort_order, color, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (slug, label, working_dir, int(enabled), int(is_default),
             sort_order, color, ts, ts),
        )
        proj = await self.get_by_slug(slug)
        assert proj is not None
        return proj

    async def update(self, project_id: int, **kwargs) -> None:
        if not kwargs:
            return
        allowed = {"slug", "label", "working_dir", "enabled", "is_default", "sort_order", "color"}
        sets, params = [], []
        for k, v in kwargs.items():
            if k not in allowed:
                continue
            if k in ("enabled", "is_default"):
                v = int(bool(v))
            sets.append(f"{k}=?")
            params.append(v)
        if not sets:
            return
        sets.append("updated_at=?")
        params.append(_now())
        params.append(project_id)
        await self.db.execute(
            f"UPDATE projects SET {', '.join(sets)} WHERE id=?", params)

    async def delete(self, project_id: int) -> None:
        # Cascades through FKs
        await self.db.execute("DELETE FROM projects WHERE id=?", (project_id,))

    async def set_setting(self, project_id: int, key: str, value) -> None:
        await self.db.execute(
            """INSERT INTO project_settings (project_id, key, value)
               VALUES (?, ?, ?)
               ON CONFLICT(project_id, key) DO UPDATE SET value=excluded.value""",
            (project_id, key, json.dumps(value)),
        )

    async def unset_setting(self, project_id: int, key: str) -> None:
        await self.db.execute(
            "DELETE FROM project_settings WHERE project_id=? AND key=?",
            (project_id, key))

    async def get_setting(self, project_id: int, key: str):
        row = await self.db.fetch_one(
            "SELECT value FROM project_settings WHERE project_id=? AND key=?",
            (project_id, key))
        return json.loads(row["value"]) if row else None

    async def all_settings(self, project_id: int) -> dict:
        rows = await self.db.fetch_all(
            "SELECT key, value FROM project_settings WHERE project_id=?",
            (project_id,))
        return {r["key"]: json.loads(r["value"]) for r in rows}

    @staticmethod
    def scan_projects_root(root: str) -> list[dict]:
        """List immediate subdirectories. Returns dicts with suggested slug, label, has_claude."""
        p = Path(root)
        if not p.exists() or not p.is_dir():
            return []
        out = []
        for entry in sorted(p.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue
            has_claude = (entry / ".claude").is_dir()
            out.append({
                "path": str(entry),
                "name": entry.name,
                "suggested_slug": entry.name,
                "suggested_label": entry.name,
                "has_claude": has_claude,
            })
        return out

    async def import_from_scan(
        self, items: list[dict], default_slug: Optional[str] = None,
    ) -> list[Project]:
        """Idempotent: skip items whose slug OR working_dir already exists.
        Re-running setup with the same projects_root is a no-op (safe to retry
        after partial failure)."""
        existing_projects = await self.list_all()
        existing_slugs = {p.slug for p in existing_projects}
        existing_paths = {p.working_dir for p in existing_projects}
        seen_in_batch_paths: set[str] = set()
        created: list[Project] = []
        for it in items:
            wd = it["working_dir"]
            if wd in existing_paths or wd in seen_in_batch_paths:
                continue  # already registered or duplicate within batch
            seen_in_batch_paths.add(wd)

            # Auto-suffix only used when two DIFFERENT working_dirs share a basename
            slug = it["slug"]
            base = slug
            n = 1
            while slug in existing_slugs:
                n += 1
                slug = f"{base}-{n}"
            existing_slugs.add(slug)

            proj = await self.create(
                slug=slug,
                label=it.get("label", slug),
                working_dir=wd,
                enabled=bool(it.get("enabled", True)),
                is_default=(slug == default_slug),
            )
            created.append(proj)
        return created
```

- [ ] **Step 2: Wire ProjectsService into lifespan**

Update `dreaming/main.py`:

```python
from dreaming.services.projects import ProjectsService

# inside lifespan, after db.connect():
app.state.projects = ProjectsService(app.state.db)
```

- [ ] **Step 3: Smoke-test via standalone script**

Create `scripts/smoke_scan.py`:

```python
"""Smoke check: scan projects_root and list discovered dirs."""
import asyncio
from pathlib import Path
import sys

# Ensure repo root on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services.db import SqliteDB
from dreaming.services.projects import ProjectsService


async def main() -> int:
    db = SqliteDB("data/dreaming.db")
    await db.connect()
    try:
        items = ProjectsService.scan_projects_root(r"D:\Work\micode")
        print(f"Found {len(items)} dirs")
        for it in items:
            print(f"  {it['name']:30} has_claude={it['has_claude']}")
        return 0 if items else 1
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

Run:

```bash
python scripts/smoke_scan.py
```

Expected: prints 11 directories (matches `d:\Work\micode\` inventory: accounting-ai-agent, ai-budget-assistant, ai-dreaming-center, dn-parser, generate-invoice, logos, marketing-ai-assistant, mi-code-ai, openwebui-ts-embedded-sdk, testing-ai-assistant, wishlist).

- [ ] **Step 4: Commit**

```bash
git add dreaming/services/projects.py dreaming/main.py scripts/smoke_scan.py
git commit -m "feat: ProjectsService — CRUD + idempotent scan_projects_root"
```

---

### Task 6: `services/config_resolver.py` — override-with-fallback

**Files:**
- Create: `dreaming/services/config_resolver.py`
- Modify: `dreaming/main.py`

- [ ] **Step 1: Create `dreaming/services/config_resolver.py`**

```python
"""Config resolver — per-project override → global default → ALC default."""
from __future__ import annotations
from typing import Any, Optional
from dreaming.services.projects import ProjectsService, Project


_SENTINEL = object()


class ConfigResolver:
    """Per-request resolver. Cache project_settings dict per project to avoid N+1."""

    def __init__(self, projects: ProjectsService, global_settings):
        self.projects = projects
        self.global_settings = global_settings
        self._cache: dict[int, dict] = {}

    async def _project_settings(self, project: Project) -> dict:
        if project.id not in self._cache:
            self._cache[project.id] = await self.projects.all_settings(project.id)
        return self._cache[project.id]

    async def get(
        self, project: Optional[Project], key: str, default: Any = _SENTINEL,
    ) -> Any:
        if project is not None:
            ps = await self._project_settings(project)
            if key in ps:
                return ps[key]
        gv = getattr(self.global_settings, key, _SENTINEL)
        if gv is not _SENTINEL:
            return gv
        if default is _SENTINEL:
            return None
        return default

    def invalidate_project(self, project_id: int) -> None:
        self._cache.pop(project_id, None)
```

- [ ] **Step 2: Wire into lifespan as a per-request dependency factory**

Update `dreaming/main.py`:

```python
from dreaming.services.config_resolver import ConfigResolver

# Inside lifespan, after projects service init:
# (no singleton resolver — fresh per request)

# Add a request-scoped factory near app definition:
def get_resolver(request) -> ConfigResolver:
    return ConfigResolver(request.app.state.projects, request.app.state.settings)

app.state.resolver_factory = get_resolver
```

- [ ] **Step 3: Verify import**

```bash
python -c "from dreaming.services.config_resolver import ConfigResolver; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add dreaming/services/config_resolver.py dreaming/main.py
git commit -m "feat: ConfigResolver — override-with-fallback"
```

---

## Phase 0.4 — Middleware

### Task 7: `middleware/setup_gate.py` — redirect to /setup if no projects

**Files:**
- Create: `dreaming/middleware/__init__.py` (empty)
- Create: `dreaming/middleware/setup_gate.py`
- Modify: `dreaming/main.py` (register middleware)

- [ ] **Step 1: Create `dreaming/middleware/__init__.py`** (empty)

- [ ] **Step 2: Create `dreaming/middleware/setup_gate.py`**

```python
"""If `projects` table is empty AND request is not for /setup or /static or /health,
redirect to /setup."""
from __future__ import annotations
from fastapi import Request
from starlette.responses import RedirectResponse


_BYPASS_PREFIXES = ("/setup", "/static", "/health", "/api", "/docs", "/redoc", "/openapi")


async def setup_gate_middleware(request: Request, call_next):
    path = request.url.path
    if any(path.startswith(p) for p in _BYPASS_PREFIXES):
        return await call_next(request)

    projects = await request.app.state.projects.list_all()
    if not projects:
        return RedirectResponse(url="/setup", status_code=303)
    return await call_next(request)
```

- [ ] **Step 3: Register middleware in `main.py`**

```python
from dreaming.middleware.setup_gate import setup_gate_middleware
app.middleware("http")(setup_gate_middleware)
```

- [ ] **Step 4: Smoke-test**

```bash
rm -f data/dreaming.db
python -m uvicorn dreaming.main:app --port 8086 &
sleep 2
curl -i http://localhost:8086/
```

Expected: `HTTP/1.1 303 See Other` + `Location: /setup`.

```bash
curl -i http://localhost:8086/health
```

Expected: `HTTP/1.1 200 OK`.

Stop server.

- [ ] **Step 5: Commit**

```bash
git add dreaming/middleware/
git commit -m "feat: setup_gate middleware — 303 to /setup when no projects"
```

---

### Task 8: `middleware/project_resolver.py` — parse `/p/{slug}/`

**Files:**
- Create: `dreaming/middleware/project_resolver.py`
- Modify: `dreaming/main.py`

- [ ] **Step 1: Create `dreaming/middleware/project_resolver.py`**

```python
"""Parses /p/{slug}/ prefix; sets request.state.project; 404 on unknown slug."""
from __future__ import annotations
from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response


async def project_resolver_middleware(request: Request, call_next):
    request.state.project = None
    path = request.url.path
    if not path.startswith("/p/"):
        return await call_next(request)

    parts = path.split("/", 3)  # ['', 'p', slug, rest_or_empty]
    if len(parts) < 3 or not parts[2]:
        return await call_next(request)

    slug = parts[2]
    project = await request.app.state.projects.get_by_slug(slug)
    if project is None or not project.enabled:
        templates: Jinja2Templates = request.app.state.templates
        return templates.TemplateResponse(
            "project_not_found.html",
            {"request": request, "slug": slug,
             "is_disabled": project is not None and not project.enabled},
            status_code=404,
        )
    request.state.project = project
    return await call_next(request)
```

- [ ] **Step 2: Create `dreaming/templates/project_not_found.html`** (placeholder; will be styled in later wave)

```html
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>Проект не найден</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:80px auto;">
<h1>Проект «{{ slug }}» не найден</h1>
{% if is_disabled %}
<p>Этот проект отключён в реестре.</p>
{% else %}
<p>Проверьте slug или зарегистрируйте проект.</p>
{% endif %}
<p><a href="/projects">→ к списку проектов</a></p>
</body>
</html>
```

- [ ] **Step 3: Wire Jinja2Templates and middleware in `main.py`**

```python
from fastapi.templating import Jinja2Templates
from dreaming.middleware.project_resolver import project_resolver_middleware

# Inside lifespan, after settings load:
app.state.templates = Jinja2Templates(directory="dreaming/templates")

# Register middleware ORDER MATTERS: project_resolver runs INSIDE setup_gate.
# Starlette executes middleware in REVERSE registration order on the way IN.
# We want setup_gate to run FIRST (outer), so register it LAST.
app.middleware("http")(project_resolver_middleware)
app.middleware("http")(setup_gate_middleware)
```

- [ ] **Step 4: Smoke-test**

Create `scripts/smoke_seed_one.py` (used by this task and Task 11 Scenario B):

```python
"""Seed exactly one project for smoke tests that need a known slug."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services.db import SqliteDB
from dreaming.services.projects import ProjectsService


async def main(slug: str = "test", working_dir: str = r"D:\Work\micode\mi-code-ai") -> int:
    db = SqliteDB("data/dreaming.db")
    await db.connect()
    try:
        svc = ProjectsService(db)
        existing = await svc.get_by_slug(slug)
        if existing is None:
            await svc.create(slug=slug, label=slug, working_dir=working_dir)
            print(f"created {slug}")
        else:
            print(f"{slug} already exists, skipped")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(*sys.argv[1:])))
```

Run:

```bash
rm -f data/dreaming.db
python scripts/smoke_seed_one.py
python -m uvicorn dreaming.main:app --port 8086 &
SERVER_PID=$!
sleep 3
curl -s -o /tmp/p404.html -w '%{http_code}\n' http://localhost:8086/p/UNKNOWN/
grep -q "не найден" /tmp/p404.html && echo "BODY OK" || echo "FAIL: 404 body missing"
kill $SERVER_PID 2>/dev/null
```

Expected: prints `404` then `BODY OK`.

- [ ] **Step 5: Commit**

```bash
git add dreaming/middleware/project_resolver.py dreaming/templates/project_not_found.html dreaming/main.py scripts/smoke_seed_one.py
git commit -m "feat: project_resolver middleware — /p/{slug}/ resolution + 404 page"
```

---

## Phase 0.5 — i18n infrastructure

### Task 9: `services/i18n.py` + Jinja `t()` filter + plural rules

**Files:**
- Create: `dreaming/i18n/__init__.py`
- Create: `dreaming/i18n/messages_ru.json`
- Create: `dreaming/i18n/messages_en.json`
- Create: `dreaming/services/i18n.py`
- Modify: `dreaming/main.py`

- [ ] **Step 1: Create empty translation files**

`dreaming/i18n/__init__.py` — empty.

`dreaming/i18n/messages_ru.json`:
```json
{
  "common.app_name": "AI Dreaming Center",
  "common.locale.ru": "Русский",
  "common.locale.en": "English",
  "navbar.all_projects": "Все проекты",
  "navbar.add_project": "+ Добавить проект",
  "projects.title": "Проекты",
  "projects.empty": "Нет зарегистрированных проектов",
  "setup.title": "Первичная настройка",
  "settings.title": "Глобальные настройки"
}
```

`dreaming/i18n/messages_en.json`:
```json
{
  "common.app_name": "AI Dreaming Center",
  "common.locale.ru": "Русский",
  "common.locale.en": "English",
  "navbar.all_projects": "All Projects",
  "navbar.add_project": "+ Add project",
  "projects.title": "Projects",
  "projects.empty": "No projects registered",
  "setup.title": "First-Time Setup",
  "settings.title": "Global Settings"
}
```

- [ ] **Step 2: Create `dreaming/services/i18n.py`**

```python
"""Lightweight i18n: load JSON dicts, provide t() with optional plural support."""
from __future__ import annotations
import json
from pathlib import Path


_DEFAULT_LOCALE = "ru"
_FALLBACK_LOCALE = "ru"


class I18n:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.messages: dict[str, dict[str, str]] = {}
        for locale in ("ru", "en"):
            p = base_dir / f"messages_{locale}.json"
            if p.exists():
                self.messages[locale] = json.loads(p.read_text(encoding="utf-8"))
            else:
                self.messages[locale] = {}

    def t(self, key: str, locale: str | None = None, **fmt) -> str:
        loc = locale or _DEFAULT_LOCALE
        msg = self.messages.get(loc, {}).get(key)
        if msg is None and loc != _FALLBACK_LOCALE:
            msg = self.messages.get(_FALLBACK_LOCALE, {}).get(key)
        if msg is None:
            return key
        if fmt:
            try:
                return msg.format(**fmt)
            except (KeyError, IndexError):
                return msg
        return msg

    def plural(self, key_base: str, n: int, locale: str | None = None) -> str:
        loc = locale or _DEFAULT_LOCALE
        category = russian_plural(n) if loc == "ru" else english_plural(n)
        return self.t(f"{key_base}.{category}", locale=loc, n=n)


def russian_plural(n: int) -> str:
    """CLDR rules for Russian counts."""
    n = abs(int(n))
    mod10, mod100 = n % 10, n % 100
    if mod10 == 1 and mod100 != 11:
        return "one"
    if mod10 in (2, 3, 4) and mod100 not in (12, 13, 14):
        return "few"
    return "many"


def english_plural(n: int) -> str:
    return "one" if abs(int(n)) == 1 else "other"
```

- [ ] **Step 3: Wire into `main.py` and register Jinja filters**

```python
from pathlib import Path
from dreaming.services.i18n import I18n

# inside lifespan:
app.state.i18n = I18n(Path("dreaming/i18n"))

# after templates init:
def _t(key: str, locale: str | None = None, **fmt) -> str:
    return app.state.i18n.t(key, locale=locale, **fmt)

app.state.templates.env.filters["t"] = _t
```

For requests to know the active locale, add a small helper in `main.py`:

```python
from fastapi import Request

def get_locale(request: Request) -> str:
    return request.cookies.get("dc_locale") or app.state.settings.default_locale
```

And update `_t` to accept the locale from a dependency at template-render-time. Simplest option: keep the filter API as-is, and have every route pass `locale` explicitly in the render context (the route handlers in Tasks 11-14 already do `locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)`). `base.html` then uses `{{ "key" | t(locale=locale) }}`. As a safety net, the first line inside `<html>` of `base.html` can include `{% set locale = locale|default('ru') %}` — see Task 11 Step 3.

- [ ] **Step 4: Smoke test via standalone script**

Create `scripts/smoke_i18n.py`:

```python
"""Smoke check: i18n loader + Russian plural rules."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services.i18n import I18n, russian_plural


def main() -> int:
    i = I18n(Path(__file__).resolve().parent.parent / "dreaming" / "i18n")
    assert i.t("navbar.all_projects", "ru") == "Все проекты"
    assert i.t("navbar.all_projects", "en") == "All Projects"
    assert i.t("missing.key", "en") == "missing.key"

    # CLDR Russian plurals
    assert russian_plural(0) == "many"
    assert russian_plural(1) == "one"
    assert russian_plural(2) == "few"
    assert russian_plural(5) == "many"
    assert russian_plural(11) == "many"
    assert russian_plural(12) == "many"
    assert russian_plural(13) == "many"
    assert russian_plural(14) == "many"
    assert russian_plural(15) == "many"
    assert russian_plural(21) == "one"
    assert russian_plural(22) == "few"
    assert russian_plural(25) == "many"
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run:

```bash
python scripts/smoke_i18n.py
```

Expected: prints `ok`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add dreaming/i18n/ dreaming/services/i18n.py dreaming/main.py scripts/smoke_i18n.py
git commit -m "feat: i18n loader + Jinja t() filter + CLDR Russian plurals"
```

---

### Task 10: `scripts/check_i18n.py` — key parity verifier

**Files:**
- Create: `scripts/check_i18n.py`

- [ ] **Step 1: Create the script**

```python
"""Fail with non-zero exit if RU and EN locales have different keys."""
import json
import sys
from pathlib import Path


def main() -> int:
    base = Path(__file__).resolve().parent.parent / "dreaming" / "i18n"
    ru = json.loads((base / "messages_ru.json").read_text(encoding="utf-8"))
    en = json.loads((base / "messages_en.json").read_text(encoding="utf-8"))
    ru_keys, en_keys = set(ru), set(en)
    only_ru = ru_keys - en_keys
    only_en = en_keys - ru_keys
    if not (only_ru or only_en):
        print("OK: locales have identical key sets")
        return 0
    if only_ru:
        print(f"In RU but not EN ({len(only_ru)}):")
        for k in sorted(only_ru):
            print(f"  - {k}")
    if only_en:
        print(f"In EN but not RU ({len(only_en)}):")
        for k in sorted(only_en):
            print(f"  - {k}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it**

```bash
python scripts/check_i18n.py
```

Expected: `OK: locales have identical key sets` + exit 0.

- [ ] **Step 3: Commit**

```bash
git add scripts/check_i18n.py
git commit -m "chore: i18n key-parity verifier"
```

---

## Phase 0.6 — Routes

### Task 11: `routes/root.py` — `/health`, `/`, base nav

**Files:**
- Create: `dreaming/routes/__init__.py` (empty)
- Create: `dreaming/routes/root.py`
- Create: `dreaming/templates/base.html`
- Create: `dreaming/templates/_navbar.html`
- Create: `dreaming/templates/index_placeholder.html`
- Create: `dreaming/static/app.css` (placeholder)
- Modify: `dreaming/main.py` (mount router and /static)

- [ ] **Step 1: Create `dreaming/routes/__init__.py`** (empty)

- [ ] **Step 2: Create `dreaming/static/app.css`**

```css
/* Placeholder; full styling in Wave 5. Tailwind via CDN handles most cases. */
body { font-family: system-ui, sans-serif; }
.muted { color: #64748b; }
```

- [ ] **Step 3: Create `dreaming/templates/base.html`**

```html
{% set locale = locale|default('ru') %}
<!DOCTYPE html>
<html lang="{{ locale }}">
<head>
  <meta charset="utf-8">
  <title>{{ "common.app_name" | t(locale=locale) }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="/static/app.css">
  <script src="https://unpkg.com/htmx.org@2"></script>
</head>
<body class="bg-slate-50 min-h-screen">
  {% include "_navbar.html" %}
  <main class="max-w-7xl mx-auto p-6">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

- [ ] **Step 4: Create `dreaming/templates/_navbar.html`** (project selector is placeholder; populated when there are projects)

```html
<nav class="bg-white border-b border-slate-200 shadow-sm">
  <div class="max-w-7xl mx-auto p-4 flex items-center gap-4">
    <a href="/" class="font-bold text-slate-900">{{ "common.app_name" | t(locale=locale) }}</a>
    {% if projects %}
    <select onchange="(()=>{const slug=event.target.value; if(slug==='*'){location.href='/'} else if(slug==='+'){location.href='/projects?new=1'} else {const cur=location.pathname; const m=cur.match(/^\/p\/[^\/]+(\/.*)?$/); location.href='/p/'+slug+(m && m[1] ? m[1] : '/');}})()"
            class="border rounded px-2 py-1">
      {% if request.state.project %}
        <option disabled>{{ request.state.project.label }}</option>
      {% endif %}
      <option value="*">● {{ "navbar.all_projects" | t(locale=locale) }}</option>
      {% for p in projects %}
        <option value="{{ p.slug }}"{% if request.state.project and request.state.project.id == p.id %} selected{% endif %}>{{ p.label }}</option>
      {% endfor %}
      <option value="+">{{ "navbar.add_project" | t(locale=locale) }}</option>
    </select>
    {% endif %}
    <div class="ml-auto flex items-center gap-2">
      <a href="/projects" class="text-sm text-slate-600 hover:text-slate-900">{{ "projects.title" | t(locale=locale) }}</a>
      <a href="/settings" class="text-sm text-slate-600 hover:text-slate-900">{{ "settings.title" | t(locale=locale) }}</a>
      <form method="post" action="/locale" class="ml-2">
        <input type="hidden" name="next" value="{{ request.url.path }}">
        <button name="locale" value="{{ 'en' if locale=='ru' else 'ru' }}"
                class="text-xs border rounded px-2 py-1">{{ 'EN' if locale=='ru' else 'RU' }}</button>
      </form>
    </div>
  </div>
</nav>
```

- [ ] **Step 5: Create `dreaming/templates/index_placeholder.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1 class="text-2xl font-bold mb-4">{{ "common.app_name" | t(locale=locale) }}</h1>
<p class="muted">Wave 0 placeholder. Aggregated dashboard arrives in Wave 5.</p>
<p class="mt-4">
  <a class="text-blue-600 underline" href="/projects">{{ "projects.title" | t(locale=locale) }}</a>
</p>
{% endblock %}
```

- [ ] **Step 6: Create `dreaming/routes/root.py`**

```python
"""Root-level routes: /, /health, /locale."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse


router = APIRouter()


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})


@router.get("/")
async def index(request: Request):
    projects = await request.app.state.projects.list_all(only_enabled=True)
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    return request.app.state.templates.TemplateResponse(
        "index_placeholder.html",
        {"request": request, "projects": projects, "locale": locale},
    )


@router.post("/locale")
async def set_locale(request: Request, locale: str = Form(...), next: str = Form("/")):
    if locale not in ("ru", "en"):
        locale = "ru"
    resp = RedirectResponse(url=next or "/", status_code=303)
    resp.set_cookie("dc_locale", locale, max_age=60 * 60 * 24 * 365, httponly=False, samesite="lax")
    return resp
```

- [ ] **Step 7: Mount router in `main.py`**

```python
from dreaming.routes.root import router as root_router

app.include_router(root_router)

# Mount /static
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="dreaming/static"), name="static")
```

- [ ] **Step 8: Smoke-test (two scenarios)**

Scenario A — empty DB → root redirects to setup:

```bash
rm -f data/dreaming.db
python -m uvicorn dreaming.main:app --port 8086 &
SERVER_PID=$!
sleep 3
test "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8086/)" = "303"
kill $SERVER_PID 2>/dev/null
```

Expected: 303 (setup_gate redirected `/` because no projects exist).

Scenario B — seed one project, then root renders the placeholder (uses the seed script created in Task 8 Step 4):

```bash
rm -f data/dreaming.db
python scripts/smoke_seed_one.py
python -m uvicorn dreaming.main:app --port 8086 &
SERVER_PID=$!
sleep 3
curl -s http://localhost:8086/ | grep -q "Wave 0 placeholder" && echo "OK"
kill $SERVER_PID 2>/dev/null
```

Expected: prints `OK`.

- [ ] **Step 9: Commit**

```bash
git add dreaming/routes/__init__.py dreaming/routes/root.py
git add dreaming/templates/base.html dreaming/templates/_navbar.html dreaming/templates/index_placeholder.html
git add dreaming/static/app.css dreaming/main.py
git commit -m "feat: root routes, base template, navbar with project selector"
```

---

### Task 12: `routes/setup.py` — multi-step wizard

**Files:**
- Create: `dreaming/routes/setup.py`
- Create: `dreaming/templates/setup.html`
- Modify: `dreaming/main.py` (mount router)

- [ ] **Step 1: Create `dreaming/templates/setup.html`** (single-page wizard with three sections)

```html
<!DOCTYPE html>
<html lang="{{ locale }}">
<head>
  <meta charset="utf-8">
  <title>{{ "setup.title" | t(locale=locale) }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50">
<main class="max-w-3xl mx-auto p-8">
  <h1 class="text-3xl font-bold mb-6">{{ "setup.title" | t(locale=locale) }}</h1>

  <form method="post" action="/setup" class="space-y-6">
    <section class="bg-white p-6 rounded shadow">
      <h2 class="text-xl font-semibold mb-3">1. Глобальные настройки</h2>
      <label class="block mb-3">
        <span class="text-sm">claude_path</span>
        <input name="claude_path" value="{{ defaults.claude_path }}" class="block w-full border rounded p-2">
      </label>
      <label class="block mb-3">
        <span class="text-sm">projects_root</span>
        <input name="projects_root" value="{{ defaults.projects_root }}" class="block w-full border rounded p-2">
      </label>
      <label class="block">
        <span class="text-sm">default_locale</span>
        <select name="default_locale" class="block w-full border rounded p-2">
          <option value="ru" {% if defaults.default_locale=='ru' %}selected{% endif %}>Русский</option>
          <option value="en" {% if defaults.default_locale=='en' %}selected{% endif %}>English</option>
        </select>
      </label>
    </section>

    {% if scan %}
    <section class="bg-white p-6 rounded shadow">
      <h2 class="text-xl font-semibold mb-3">2. Найденные проекты в {{ scan_root }}</h2>
      <table class="w-full text-sm">
        <thead><tr class="text-left border-b">
          <th class="p-1">включить</th>
          <th class="p-1">по&nbsp;умолч.</th>
          <th class="p-1">slug</th>
          <th class="p-1">label</th>
          <th class="p-1">путь</th>
          <th class="p-1">.claude</th>
        </tr></thead>
        <tbody>
        {% for it in scan %}
        <tr class="border-b">
          <td class="p-1"><input type="checkbox" name="enabled_{{ loop.index0 }}" {% if it.has_claude %}checked{% endif %}></td>
          <td class="p-1"><input type="radio" name="default_idx" value="{{ loop.index0 }}" {% if loop.first %}checked{% endif %}></td>
          <td class="p-1"><input name="slug_{{ loop.index0 }}" value="{{ it.suggested_slug }}" class="border rounded p-1 w-full"></td>
          <td class="p-1"><input name="label_{{ loop.index0 }}" value="{{ it.suggested_label }}" class="border rounded p-1 w-full"></td>
          <td class="p-1"><input name="path_{{ loop.index0 }}" value="{{ it.path }}" class="border rounded p-1 w-full" readonly></td>
          <td class="p-1">{{ "✓" if it.has_claude else "" }}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
      <input type="hidden" name="scan_count" value="{{ scan|length }}">
      <p class="text-sm muted mt-3">{{ scan|length }} проектов найдено. Включённые — будут импортированы.</p>
    </section>
    <button class="bg-blue-600 text-white px-4 py-2 rounded">Сохранить и импортировать</button>
    {% else %}
    <button name="action" value="scan" class="bg-blue-600 text-white px-4 py-2 rounded">Просканировать projects_root</button>
    {% endif %}
  </form>
</main>
</body>
</html>
```

- [ ] **Step 2: Create `dreaming/routes/setup.py`**

```python
"""Multi-step (single page, two phases) setup wizard."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
import yaml

from dreaming.services.projects import ProjectsService


router = APIRouter()


def _save_global_yaml(values: dict) -> None:
    """Merge values into config.yaml (create if missing)."""
    p = Path("config.yaml")
    cur = {}
    if p.exists():
        cur = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    cur.update(values)
    p.write_text(yaml.safe_dump(cur, allow_unicode=True), encoding="utf-8")


@router.get("/setup")
async def setup_get(request: Request):
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    return request.app.state.templates.TemplateResponse(
        "setup.html",
        {
            "request": request,
            "defaults": request.app.state.settings,
            "scan": None,
            "scan_root": None,
            "locale": locale,
        },
    )


@router.post("/setup")
async def setup_post(request: Request):
    form = await request.form()
    action = form.get("action")
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)

    # Phase 1: scan only (preserve newly entered global settings in form)
    if action == "scan":
        root = (form.get("projects_root") or "").strip()
        scan = ProjectsService.scan_projects_root(root) if root else []
        defaults = type("D", (), dict(
            claude_path=form.get("claude_path", request.app.state.settings.claude_path),
            projects_root=root or request.app.state.settings.projects_root,
            default_locale=form.get("default_locale", request.app.state.settings.default_locale),
        ))()
        return request.app.state.templates.TemplateResponse(
            "setup.html",
            {"request": request, "defaults": defaults, "scan": scan,
             "scan_root": root, "locale": locale},
        )

    # Phase 2: persist globals + import selected projects
    globals_to_save = {
        "claude_path": form.get("claude_path", "").strip() or "claude",
        "projects_root": form.get("projects_root", "").strip(),
        "default_locale": form.get("default_locale", "ru"),
    }
    _save_global_yaml(globals_to_save)
    request.app.state.settings = type(request.app.state.settings).load()

    n = int(form.get("scan_count", 0))
    default_idx = form.get("default_idx")
    items = []
    for i in range(n):
        if not form.get(f"enabled_{i}"):
            continue
        items.append({
            "slug": form.get(f"slug_{i}", "").strip(),
            "label": form.get(f"label_{i}", "").strip(),
            "working_dir": form.get(f"path_{i}", "").strip(),
            "enabled": True,
        })

    if items:
        default_slug = None
        if default_idx is not None:
            try:
                idx = int(default_idx)
                if form.get(f"enabled_{idx}"):
                    default_slug = form.get(f"slug_{idx}", "").strip()
            except ValueError:
                pass
        await request.app.state.projects.import_from_scan(items, default_slug=default_slug)

    return RedirectResponse(url="/", status_code=303)
```

- [ ] **Step 3: Mount router in `main.py`**

```python
from dreaming.routes.setup import router as setup_router
app.include_router(setup_router)
```

- [ ] **Step 4: Smoke-test**

```bash
rm -f data/dreaming.db config.yaml
python -m uvicorn dreaming.main:app --port 8086 &
sleep 2

# Step 1: open setup
curl -s http://localhost:8086/setup | grep "Просканировать"

# Step 2: scan projects_root via real form-post (pretend GET, then click "scan")
curl -s -X POST http://localhost:8086/setup \
  -d "action=scan" \
  -d "claude_path=claude" \
  -d "projects_root=D:\\Work\\micode" \
  -d "default_locale=ru" | grep "Найденные проекты"
```

Expected: HTML contains `Найденные проекты в D:\Work\micode` and lists ~11 entries with `mi-code-ai`, `wishlist`, etc.

Stop server.

- [ ] **Step 5: Commit**

```bash
git add dreaming/routes/setup.py dreaming/templates/setup.html dreaming/main.py
git commit -m "feat: setup wizard — global config + projects_root scan + bulk import"
```

---

### Task 13: `routes/projects.py` — list/CRUD

**Files:**
- Create: `dreaming/routes/projects.py`
- Create: `dreaming/templates/projects.html`
- Modify: `dreaming/main.py` (mount router)

- [ ] **Step 1: Create `dreaming/templates/projects.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1 class="text-2xl font-bold mb-4">{{ "projects.title" | t(locale=locale) }}</h1>

{% if projects %}
<table class="w-full bg-white rounded shadow text-sm">
  <thead class="text-left border-b"><tr>
    <th class="p-2">slug</th>
    <th class="p-2">label</th>
    <th class="p-2">working_dir</th>
    <th class="p-2">enabled</th>
    <th class="p-2">default</th>
    <th class="p-2"></th>
  </tr></thead>
  <tbody>
  {% for p in projects %}
  <tr class="border-b">
    <td class="p-2 font-mono">{{ p.slug }}</td>
    <td class="p-2">{{ p.label }}</td>
    <td class="p-2 text-xs muted">{{ p.working_dir }}</td>
    <td class="p-2">{{ "✓" if p.enabled else "—" }}</td>
    <td class="p-2">{{ "★" if p.is_default else "" }}</td>
    <td class="p-2">
      <form method="post" action="/projects/{{ p.id }}/toggle" class="inline">
        <button class="text-xs px-2 py-1 border rounded">{{ "Disable" if p.enabled else "Enable" }}</button>
      </form>
      <form method="post" action="/projects/{{ p.id }}/delete" class="inline"
            onsubmit="return prompt('Введите slug `{{ p.slug }}` чтобы удалить:')==='{{ p.slug }}'">
        <button class="text-xs px-2 py-1 border rounded text-red-600">Delete</button>
      </form>
    </td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}
<p class="muted">{{ "projects.empty" | t(locale=locale) }}</p>
<p class="mt-4"><a href="/setup" class="text-blue-600 underline">→ /setup</a></p>
{% endif %}

<div class="mt-6 bg-white p-4 rounded shadow">
  <h2 class="font-semibold mb-2">Импорт из projects_root</h2>
  <form method="post" action="/projects/import">
    <input name="root" value="{{ settings.projects_root }}" class="border rounded p-1 w-96">
    <button class="bg-blue-600 text-white px-3 py-1 rounded">Просканировать и импортировать новые</button>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 2: Create `dreaming/routes/projects.py`**

```python
"""Projects CRUD."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse

from dreaming.services.projects import ProjectsService


router = APIRouter()


@router.get("/projects")
async def projects_list(request: Request):
    projects = await request.app.state.projects.list_all()
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    return request.app.state.templates.TemplateResponse(
        "projects.html",
        {"request": request, "projects": projects,
         "settings": request.app.state.settings, "locale": locale},
    )


@router.post("/projects/{project_id}/toggle")
async def projects_toggle(request: Request, project_id: int):
    p = await request.app.state.projects.get_by_id(project_id)
    if not p:
        raise HTTPException(404)
    await request.app.state.projects.update(project_id, enabled=not p.enabled)
    return RedirectResponse("/projects", status_code=303)


@router.post("/projects/{project_id}/delete")
async def projects_delete(request: Request, project_id: int):
    await request.app.state.projects.delete(project_id)
    return RedirectResponse("/projects", status_code=303)


@router.post("/projects/import")
async def projects_import(request: Request, root: str = Form(...)):
    items_meta = ProjectsService.scan_projects_root(root)
    if not items_meta:
        return RedirectResponse("/projects", status_code=303)
    items = [
        {"slug": m["suggested_slug"], "label": m["suggested_label"],
         "working_dir": m["path"], "enabled": True}
        for m in items_meta
    ]
    await request.app.state.projects.import_from_scan(items)
    return RedirectResponse("/projects", status_code=303)
```

- [ ] **Step 3: Mount router**

```python
from dreaming.routes.projects import router as projects_router
app.include_router(projects_router)
```

Note: ensure routes registered AFTER setup router so `/setup` keeps priority on path collision (none expected).

- [ ] **Step 4: Smoke test (DB pre-populated with all 11 projects)**

```bash
rm -f data/dreaming.db
python scripts/smoke_setup.py   # see Task 16; populates 11 projects
python -m uvicorn dreaming.main:app --port 8086 &
SERVER_PID=$!
sleep 3
HTML="$(curl -s http://localhost:8086/projects)"
echo "$HTML" | grep -q "mi-code-ai" || { echo "FAIL: mi-code-ai missing"; kill $SERVER_PID; exit 1; }
echo "$HTML" | grep -q "wishlist" || { echo "FAIL: wishlist missing"; kill $SERVER_PID; exit 1; }
kill $SERVER_PID 2>/dev/null
```

Expected: both greps succeed.

- [ ] **Step 5: Commit**

```bash
git add dreaming/routes/projects.py dreaming/templates/projects.html dreaming/main.py
git commit -m "feat: /projects list, toggle, delete, import"
```

---

### Task 14: `routes/settings.py` — global settings UI (read-only in W0, full UI in W1)

**Files:**
- Create: `dreaming/routes/settings.py`
- Create: `dreaming/templates/settings.html`
- Modify: `dreaming/main.py` (mount router)

- [ ] **Step 1: Create `dreaming/templates/settings.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1 class="text-2xl font-bold mb-4">{{ "settings.title" | t(locale=locale) }}</h1>
<p class="muted mb-4">Wave 0: только чтение. Полная UI — Wave 1.</p>
<form method="post" action="/settings" class="space-y-3 bg-white p-4 rounded shadow max-w-xl">
{% for k, v in current.items() %}
  <label class="block">
    <span class="text-sm font-mono">{{ k }}</span>
    <input name="{{ k }}" value="{{ v }}" class="block w-full border rounded p-1 font-mono text-sm">
  </label>
{% endfor %}
  <button class="bg-blue-600 text-white px-3 py-1 rounded">Save</button>
</form>
{% endblock %}
```

- [ ] **Step 2: Create `dreaming/routes/settings.py`**

```python
"""Global settings UI (Wave 0 minimal — Wave 1 expands to full ~80-key form)."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import yaml


router = APIRouter()


def _settings_to_dict(settings) -> dict:
    out = {}
    for f in settings.model_fields:
        out[f] = getattr(settings, f)
    return out


def _save_yaml(values: dict) -> None:
    p = Path("config.yaml")
    cur = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    cur = cur or {}
    cur.update(values)
    p.write_text(yaml.safe_dump(cur, allow_unicode=True), encoding="utf-8")


@router.get("/settings")
async def settings_get(request: Request):
    locale = request.cookies.get("dc_locale", request.app.state.settings.default_locale)
    return request.app.state.templates.TemplateResponse(
        "settings.html",
        {"request": request, "current": _settings_to_dict(request.app.state.settings),
         "locale": locale, "projects": []},
    )


@router.post("/settings")
async def settings_post(request: Request):
    form = await request.form()
    new_values = {}
    for k in request.app.state.settings.model_fields:
        if k in form:
            new_values[k] = form[k]
    _save_yaml(new_values)
    request.app.state.settings = type(request.app.state.settings).load()
    return RedirectResponse("/settings", status_code=303)
```

- [ ] **Step 3: Mount router**

```python
from dreaming.routes.settings import router as settings_router
app.include_router(settings_router)
```

- [ ] **Step 4: Smoke test**

```bash
python -m uvicorn dreaming.main:app --port 8086 &
sleep 2
curl -s http://localhost:8086/settings | grep "claude_path"
```

Stop server.

- [ ] **Step 5: Commit**

```bash
git add dreaming/routes/settings.py dreaming/templates/settings.html dreaming/main.py
git commit -m "feat: /settings minimal UI (Wave 1 expands)"
```

---

## Phase 0.7 — Stubs for downstream waves

### Task 15: Service stubs

**Files:**
- Create: `dreaming/services/process_manager.py` (stub)
- Create: `dreaming/services/orchestration_hub.py` (stub)
- Create: `dreaming/services/claude_session_tail.py` (stub)
- Create: `dreaming/services/subagent_watcher.py` (stub)
- Create: `dreaming/services/subagent_backfill.py` (stub)
- Create: `dreaming/services/scheduler.py` (Wave 0 minimal)
- Modify: `dreaming/main.py` (wire stubs into lifespan; start/shutdown scheduler)

- [ ] **Step 1: Create `dreaming/services/process_manager.py`**

```python
"""Stub for Wave 1+. Public API mirrors ALC's ProcessManager but raises NotImplementedError
for spawn-related calls. Allows downstream imports in Wave 0.

NOTE for Wave 1 implementer:
- Add per-project FIFO queue (dict[project_id, list[QueuedTask]]) and global semaphore
  for `max_concurrent`; per-project semaphore for `max_concurrent_per_project`.
- Add `keep_awake: KeepAwake` attribute (Windows Modern Standby suppressor) — owned
  by ProcessManager, not app.state, per spec singleton inventory.
- See spec § "Process Manager" and "Concurrency".
"""
from __future__ import annotations


class ProcessManager:
    def __init__(self, settings, db, projects):
        self.settings = settings
        self.db = db
        self.projects = projects
        self.running: dict[str, dict] = {}
        # Wave 1: queue, semaphores, keep_awake go here.

    async def start_session(self, project, agent_name: str, **kwargs) -> str:
        raise NotImplementedError("ProcessManager.start_session implemented in Wave 1")

    async def start_command(self, project, command_name: str, prompt: str, **kwargs) -> str:
        raise NotImplementedError("ProcessManager.start_command implemented in Wave 1")

    async def kill(self, key: str) -> bool:
        return False

    async def reconcile_stale_sessions(self, active_pairs: list[tuple[int, str]]) -> int:
        """active_pairs: list of (project_id, agent_name) tuples — see spec.
        Wave 0 stub: noop."""
        return 0
```

- [ ] **Step 2: Create `dreaming/services/orchestration_hub.py`**

```python
"""Stub for Wave 3."""


class OrchestrationHub:
    def __init__(self, db, projects):
        self.db = db
        self.projects = projects

    async def publish(self, project_id: int, run_id: str, event_type: str, payload: dict) -> None:
        raise NotImplementedError("OrchestrationHub.publish implemented in Wave 3")
```

- [ ] **Step 3: Create `dreaming/services/claude_session_tail.py`**

```python
"""Stub for Wave 3."""


class ClaudeSessionTail:
    def __init__(self, *args, **kwargs):
        pass

    async def start(self) -> None:
        raise NotImplementedError("ClaudeSessionTail implemented in Wave 3")

    async def stop(self) -> None:
        return
```

- [ ] **Step 4: Create `dreaming/services/subagent_watcher.py`**

```python
"""Stub for Wave 3."""


class SubagentWatcher:
    def __init__(self, *args, **kwargs):
        pass

    async def start(self) -> None:
        raise NotImplementedError("SubagentWatcher implemented in Wave 3")

    async def stop(self) -> None:
        return
```

- [ ] **Step 5: Create `dreaming/services/subagent_backfill.py`**

```python
"""Stub for Wave 3."""


async def backfill_run(run_id: str, db) -> int:
    raise NotImplementedError("backfill_run implemented in Wave 3")
```

- [ ] **Step 6: Create `dreaming/services/scheduler.py` (Wave 0 minimal)**

```python
"""Wave 0: only the global reconcile_stale_sessions interval runs.
Per-project crons land in Wave 1+."""
from __future__ import annotations
from apscheduler.schedulers.asyncio import AsyncIOScheduler


def build_scheduler(app_state) -> AsyncIOScheduler:
    sched = AsyncIOScheduler()

    async def reconcile_job():
        # Wave 1+ supplies real reconcile logic via ProcessManager
        pm = app_state.process_manager
        active = list(pm.running.keys())  # in W0 always empty
        return await pm.reconcile_stale_sessions([])

    sched.add_job(reconcile_job, "interval", minutes=5, id="reconcile_stale_sessions")
    return sched
```

- [ ] **Step 7: Wire stubs into lifespan in `main.py`**

```python
from dreaming.services.process_manager import ProcessManager
from dreaming.services.orchestration_hub import OrchestrationHub
from dreaming.services.scheduler import build_scheduler

# inside lifespan, after projects + i18n setup:
app.state.process_manager = ProcessManager(
    app.state.settings, app.state.db, app.state.projects)
app.state.orchestration_hub = OrchestrationHub(app.state.db, app.state.projects)
app.state.scheduler = build_scheduler(app.state)
app.state.scheduler.start()

try:
    yield
finally:
    # Cleanup runs even on exception during the yield body.
    app.state.scheduler.shutdown(wait=False)
    await app.state.db.close()
```

- [ ] **Step 8: Smoke test — boots cleanly with all stubs wired**

```bash
python -m uvicorn dreaming.main:app --port 8086 &
sleep 2
curl -s http://localhost:8086/health
```

Expected: `{"ok":true}` and no traceback in server logs.

Stop server.

- [ ] **Step 9: Commit**

```bash
git add dreaming/services/process_manager.py dreaming/services/orchestration_hub.py
git add dreaming/services/claude_session_tail.py dreaming/services/subagent_watcher.py
git add dreaming/services/subagent_backfill.py dreaming/services/scheduler.py
git add dreaming/main.py
git commit -m "feat: stub services + minimal scheduler — public API ready for Wave 1+"
```

---

## Phase 0.8 — End-to-end smoke + tag

### Task 16: Full Wave 0 smoke run

**Files:**
- Create: `scripts/smoke_setup.py` (programmatic full-import smoke; bypasses browser form)

- [ ] **Step 1: Create `scripts/smoke_setup.py`** — programmatic version of the browser-based wizard:

```python
"""Wave 0 end-to-end smoke: scan + import all projects under projects_root.
Asserts DB has the expected count after import. Idempotent (safe to re-run)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dreaming.services.db import SqliteDB
from dreaming.services.projects import ProjectsService


PROJECTS_ROOT = r"D:\Work\micode"
DB_PATH = "data/dreaming.db"


async def main() -> int:
    db = SqliteDB(DB_PATH)
    await db.connect()
    try:
        svc = ProjectsService(db)
        scan = svc.scan_projects_root(PROJECTS_ROOT)
        print(f"Scanned: {len(scan)} dirs")
        items = [
            {"slug": s["suggested_slug"], "label": s["suggested_label"],
             "working_dir": s["path"], "enabled": True}
            for s in scan
        ]
        before = await svc.list_all()
        created = await svc.import_from_scan(items, default_slug=items[0]["slug"] if items else None)
        after = await svc.list_all()
        print(f"Before: {len(before)}; created in this run: {len(created)}; after: {len(after)}")
        # Idempotency check: re-running must not create more rows
        again = await svc.import_from_scan(items)
        final = await svc.list_all()
        assert len(final) == len(after), \
            f"Import not idempotent: {len(after)} → {len(final)}"
        print(f"After idempotency re-run: {len(final)} (unchanged ✓)")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Wipe state and run end-to-end smoke**

```bash
rm -f data/dreaming.db config.yaml
python scripts/smoke_setup.py
```

Expected: prints `Scanned: 11 dirs`, `created in this run: 11`, `After idempotency re-run: 11 (unchanged ✓)`.

- [ ] **Step 3: Verify HTTP layer end-to-end**

```bash
python -m uvicorn dreaming.main:app --port 8086 &
SERVER_PID=$!
sleep 3

# /projects lists 11 entries
N=$(curl -s http://localhost:8086/projects | grep -oE 'D:\\\\Work\\\\micode\\\\[a-z0-9-]+' | sort -u | wc -l)
test "$N" = "11" || echo "WARN: /projects shows $N entries (expected 11)"

# /p/UNKNOWN/ → 404
test "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8086/p/UNKNOWN/)" = "404"

# /p/<known>/ does not crash (no project routes mounted in W0; FastAPI returns 404)
test "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8086/p/mi-code-ai/)" = "404"

# /health
test "$(curl -s http://localhost:8086/health)" = '{"ok":true}'

# / now renders placeholder (projects exist)
curl -s http://localhost:8086/ | grep -q "Wave 0 placeholder"

# i18n parity
python scripts/check_i18n.py

kill $SERVER_PID 2>/dev/null
```

Expected: all checks pass with no `WARN`/`FAIL`. Note: `/p/<known>/` returns 404 in Wave 0 because no project routes are mounted yet — that is expected; tested only to confirm middleware passes through cleanly without exception.

Manual verification of browser flow (alternative to Step 2):

1. Stop server, run `rm -f data/dreaming.db config.yaml`.
2. `python -m uvicorn dreaming.main:app --port 8086`.
3. Open `http://localhost:8086/` → should redirect to `/setup`.
4. Set `projects_root` = `D:\Work\micode`, click "Просканировать projects_root".
5. Verify 11 directories appear with correct names.
6. Leave checkboxes default, click "Сохранить и импортировать".
7. Confirm redirect to `/` showing the placeholder.
8. Open `/projects` → confirm 11 rows.

- [ ] **Step 4: Commit smoke script**

```bash
git add scripts/smoke_setup.py
git commit -m "test(smoke): end-to-end Wave 0 import + idempotency check"
```

- [ ] **Step 5: Update `docs/smoke-tests.md`**

Replace the Wave 0 section with the actual run output (any deviations from expected).

```bash
git add docs/smoke-tests.md
git commit -m "docs: smoke-test results for Wave 0"
```

- [ ] **Step 6: Tag the wave**

```bash
git tag wave-0
```

- [ ] **Step 7: Mark plan checkboxes complete**

Via the Bash tool:

```bash
sed -i 's/^- \[ \]/- [x]/' docs/superpowers/plans/2026-05-09-wave-0-foundation.md
git add docs/superpowers/plans/2026-05-09-wave-0-foundation.md
git commit -m "docs: mark Wave 0 plan complete"
```

PowerShell equivalent:

```powershell
(Get-Content docs/superpowers/plans/2026-05-09-wave-0-foundation.md) `
  -replace '^- \[ \]', '- [x]' `
  | Set-Content -Encoding utf8 docs/superpowers/plans/2026-05-09-wave-0-foundation.md
```

---

## Acceptance criteria — Wave 0

- [ ] Server boots on 8086 with no traceback.
- [ ] `curl /health` returns `{"ok":true}`.
- [ ] First run with empty DB: `/` redirects 303 to `/setup`.
- [ ] Setup wizard scans `d:\Work\micode\` and shows 11 directories.
- [ ] Submitting wizard creates 11 rows in `projects` table.
- [ ] `/projects` lists all 11 with toggle/delete affordances.
- [ ] `/p/UNKNOWN/` returns 404 with the "проект не найден" template.
- [ ] `/p/<known-slug>/` returns whatever the project route would (Wave 0: no project routes mounted; expect 404 from FastAPI's default handler since no `/p/...` routes are registered yet — that's fine).
- [ ] Setting `dc_locale=en` cookie changes navbar text.
- [ ] `/settings` displays current global settings; saving persists to `config.yaml`.
- [ ] `python scripts/check_i18n.py` exits 0.
- [ ] Tag `wave-0` exists in git.

---

## Out of scope (handled by later waves)

- Per-project routes under `/p/{slug}/` (Wave 1+).
- Real ProcessManager implementation (Wave 1).
- Per-project crons (Wave 1+).
- Orchestration / cascade pipelines (Wave 3).
- Full ~80-key settings UI with override states (Wave 1).
- Aggregated `/` dashboard (Wave 5).
- English translation of all keys (Wave 5).
- Push to `https://github.com/micode-ai/ai-dreaming-center` (Wave 5).

---

## Notes for the executing engineer

- **No tests.** This project follows ALC's "no test suite" convention. Verify each task's output by running the smoke command listed.
- **Working dir for all commands:** `D:\Work\micode\ai-dreaming-center\`. The plan file lives there too (copied in Task 2).
- **PowerShell vs Bash:** examples use bash syntax. PowerShell equivalents:
  - `rm -f X` → `Remove-Item -Force -ErrorAction SilentlyContinue X`
  - `&` (background) → `Start-Process -NoNewWindow python -ArgumentList ...`
  - `$(...)` → `(...)` then capture
  - `sleep 2` → `Start-Sleep -Seconds 2`
  Use whichever the executor's shell supports.
- **Git commits.** Frequent and small. Each task ends with a commit. If a verification step fails, do NOT commit; fix first.
- **Stubs.** Files in `dreaming/services/` whose body raises `NotImplementedError` are deliberate. Wave 1 is the next plan.
