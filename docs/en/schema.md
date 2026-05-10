# SQLite Schema Reference

All 16 tables of the `data/dreaming.db` (SQLite in WAL mode). Source of truth: the `_SCHEMA` string in [`dreaming/services/db.py`](../../dreaming/services/db.py) (lines 23–259) + the `_migrate_orchestration` block (lines 282–348).

## Contents

- [General](#general)
- [`projects`](#projects)
- [`project_settings`](#project_settings)
- [`agent_learning_sessions`](#agent_learning_sessions)
- [`agent_learning_rotation`](#agent_learning_rotation)
- [`custom_topics`](#custom_topics)
- [`orchestrator_runs`](#orchestrator_runs)
- [`orchestrator_nodes`](#orchestrator_nodes)
- [`orchestrator_messages`](#orchestrator_messages)
- [`orchestrator_events`](#orchestrator_events)
- [`orchestrator_stages`](#orchestrator_stages)
- [`orchestrator_gate_verdicts`](#orchestrator_gate_verdicts)
- [`orchestrator_artifacts`](#orchestrator_artifacts)
- [`orchestrator_questions`](#orchestrator_questions)
- [`orchestrator_tts_messages`](#orchestrator_tts_messages)
- [`ai_usage_events`](#ai_usage_events)
- [`ai_usage_files`](#ai_usage_files)
- [Idempotent migrations](#idempotent-migrations)
- [Cascade delete](#cascade-delete)

## General

All timestamps are stored as ISO strings in UTC (format: `2026-05-09T14:33:21+00:00`). See `_now()` in [`projects.py:11`](../../dreaming/services/projects.py) and [`orchestration_hub.py:15`](../../dreaming/services/orchestration_hub.py).

PRAGMA on startup (db.py:275–276):

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
```

`foreign_keys=ON` is required — without it CASCADE wouldn't work.

WAL gives multiple readers in parallel with one writer. After startup the `data/` folder gets `.db`, `.db-wal`, `.db-shm`. Back up all three (or use the `sqlite3 .backup` API, see [`deployment.md`](deployment.md)).

Types:
- `INTEGER` — int64.
- `TEXT` — UTF-8 string.
- `REAL` — float64.

## `projects`

**Purpose**: registry of registered projects. Each project points at its `working_dir` where `.claude/agents/` lives.

```sql
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
```

| Column | Type | Null? | Description |
|---|---|---|---|
| `id` | INTEGER | NO (PK) | Auto-increment. |
| `slug` | TEXT | NO (UNIQUE) | URL-friendly identifier (used in `/p/{slug}/`). |
| `label` | TEXT | NO | Display name for the UI. |
| `working_dir` | TEXT | NO | Absolute path to the project root (where `.claude/agents/` lives). |
| `enabled` | INT | NO (def 1) | 0/1 — whether the project is disabled (`/p/{slug}/*` routes 404 on 0). |
| `is_default` | INT | NO (def 0) | 0/1 — default project for slash commands without `project_slug`. |
| `sort_order` | INT | NO (def 0) | List ordering. |
| `color` | TEXT | YES | Optional hex for UI badges. |
| `created_at` | TEXT | NO | ISO timestamp. |
| `updated_at` | TEXT | NO | ISO timestamp; bumped in `update()`. |

**Indexes**: `idx_projects_enabled (enabled, sort_order)` — for fast in-order selection of enabled projects.

**Who reads/writes**:
- `ProjectsService` ([`dreaming/services/projects.py`](../../dreaming/services/projects.py)) — all CRUD + `import_from_scan`.
- `setup_gate_middleware` — checks for at least one row.
- `project_resolver_middleware` — `get_by_slug` on every `/p/{slug}/*` request.

## `project_settings`

**Purpose**: KV overrides per project. Values are stored as JSON-encoded scalars (see `set_setting`/`get_setting` in `projects.py:109–126`).

```sql
CREATE TABLE IF NOT EXISTS project_settings (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    PRIMARY KEY (project_id, key)
);
```

- Composite PK — `(project_id, key)`. One project, one override row per key.
- ON DELETE CASCADE — deleting a project removes all overrides.
- `value` is JSON. `True`/`False` is stored as `"true"`/`"false"`, strings as `"\"text\""`, ints as `"42"`, etc.

**Who uses it**: [`ConfigResolver`](../../dreaming/services/config_resolver.py) when resolving override → fallback. Re-read per-request, cached in `_cache: dict[int, dict]` (config_resolver.py:18).

See also [`features/settings.md`](features/settings.md).

## `agent_learning_sessions`

**Purpose**: history of self-study sessions.

```sql
CREATE TABLE IF NOT EXISTS agent_learning_sessions (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
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
    ON agent_learning_sessions (project_id, started_at DESC);
```

| Column | Type | Description |
|---|---|---|
| `id` | TEXT (PK) | UUID v4. |
| `project_id` | INT (FK) | CASCADE. |
| `agent_name` | TEXT | Agent name, or `cmd:{slug}:{cmdname}` for command-style. |
| `started_at` | TEXT | ISO. |
| `finished_at` | TEXT | NULL while running. |
| `status` | TEXT | `running` (NULL allowed initially), then `success` / `no_gap` / `failed` / `timeout` / `cancelled`. |
| `tokens_total` | INT | NULL until known. |
| `model` | TEXT | `sonnet` / `haiku` / `opus`. |
| `topic` | TEXT | What was studied. |
| `note_path` | TEXT | Path to the resulting .md note. |
| `error_message` | TEXT | NULL on success. |
| `entity_page` | TEXT | Optional link to a wiki page. |
| `confidence` | REAL | 0..1. |

**Indexes**: 3 — by agent_name, by started_at DESC (across all sessions), and a compound `(project_id, started_at DESC)` for fast `/p/{slug}/` dashboards.

**Who writes**:
- `db.create_session(project_id, agent_name, model)` — `INSERT ... status='running'` (db.py:369).
- `db.get_or_create_session(...)` — reuse if there's a recent running one inside `reuse_window_sec=120` (db.py:381).
- `db.finish_session(session_id, status, ...)` — `UPDATE` finish + bumps rotation `last_studied_at` (db.py:398).
- `db.cancel_session(session_id)` — `UPDATE status='cancelled'` if it was `running` (db.py:432).
- `ProcessManager._cleanup` via `db.reconcile_stale_sessions()` — closes orphans (process_manager.py:618).

**Who reads**:
- `db.list_sessions(project_id, limit)` — last N (db.py:444).
- `db.list_running_sessions(project_id)` — only active (db.py:451).
- `db.week_stats(project_id)` — status counter from Monday UTC (db.py:459).

## `agent_learning_rotation`

**Purpose**: per-project rotation: tiers, last_studied_at, enabled flag.

```sql
CREATE TABLE IF NOT EXISTS agent_learning_rotation (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    tier INTEGER DEFAULT 2,
    last_studied_at TEXT,
    enabled INTEGER DEFAULT 1,
    PRIMARY KEY (project_id, agent_name)
);
```

PK is rebuilt around `(project_id, agent_name)` (in the ALC original the PK was just `agent_name`). This is the main dreaming-side extension of this table.

| Column | Description |
|---|---|
| `tier` | 1 / 2 / 3 — priority in the nightly pick. 1 — most often. |
| `last_studied_at` | Updated in `finish_session`. |
| `enabled` | 0 — agent is excluded from nightly. |

**Who writes**:
- `db.upsert_agent_rotation` — `INSERT OR IGNORE` (db.py:499). Never updates an existing row.
- `db.set_agent_tier` (db.py:511).
- `db.set_agent_enabled` (db.py:518).
- `db.finish_session` — UPDATE `last_studied_at` (db.py:425).

**Who reads**:
- `db.list_rotation(project_id)` — all, sorted tier ASC, name ASC (db.py:482).
- `db.next_agents_for_nightly(project_id, count)` — for the nightly_learning cron: `WHERE enabled=1 ORDER BY last_studied_at IS NOT NULL, last_studied_at ASC, tier ASC, agent_name ASC LIMIT ?` (db.py:489). Gives NULL last_studied_at first, then oldest.

## `custom_topics`

**Purpose**: user-defined topics (the kanban on `/p/{slug}/kanban`); injected into the self-study prompt by the starter-kit command.

```sql
CREATE TABLE IF NOT EXISTS custom_topics (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    module TEXT DEFAULT '',
    target_agents TEXT DEFAULT '',
    question TEXT DEFAULT '',
    why_important TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    active INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_topics_project_active
    ON custom_topics (project_id, active);
```

`target_agents` — comma-separated list, or empty (then any agent matches). See `db.list_custom_topics_for_agent` for the LIKE logic (db.py:535).

**Who writes**: `db.add_custom_topic` (db.py:545), `db.delete_custom_topic` (db.py:559).
**Who reads**: `db.list_custom_topics(project_id, active_only)` (db.py:527).

## `orchestrator_runs`

```sql
CREATE TABLE IF NOT EXISTS orchestrator_runs (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    external_id TEXT,
    goal TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_or_runs_started ON orchestrator_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_or_runs_project_started
    ON orchestrator_runs (project_id, started_at DESC);
```

| Column | Description |
|---|---|
| `id` | UUID v4 (DC-internal). |
| `external_id` | Claude session UUID — same as in `~/.claude/projects/<workdir>/<external_id>.jsonl`. Used for resume and backfill. |
| `goal` | Textual goal of the run. |
| `status` | `running` / `completed` / `failed` / `cancelled`. |

**Who writes**:
- `OrchestrationHub.create_run` (orchestration_hub.py:26).
- `OrchestrationHub.finish_run` (orchestration_hub.py:56).

**Who reads**:
- `OrchestrationHub.get_run`, `list_runs`, `has_running_run`.
- `cascade_costs.list_cascade_costs` (cascade_costs.py:21).

## `orchestrator_nodes`

```sql
CREATE TABLE IF NOT EXISTS orchestrator_nodes (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
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
    -- + dreaming via _migrate_orchestration:
    stage_id TEXT,
    FOREIGN KEY(run_id) REFERENCES orchestrator_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_or_nodes_run ON orchestrator_nodes (run_id);
CREATE INDEX IF NOT EXISTS idx_or_nodes_parent ON orchestrator_nodes (parent_node_id);
CREATE INDEX IF NOT EXISTS idx_or_nodes_project_run
    ON orchestrator_nodes (project_id, run_id);
```

`stage_id` is added via `ALTER TABLE` in `_migrate_orchestration` (db.py:287). It's a nullable text reference (no FK constraint).

| Column | Description |
|---|---|
| `external_id` | For an orch-run's root node it equals the run's `external_id` (Claude session). For a subagent — agent_hash (file name `agent-<hash>.jsonl`). |
| `parent_node_id` | NULL for root; for a subagent — id of the root node. |
| `role` | `orchestrator` / `worker` / etc. |
| `status` | `running` / `completed` / `failed` / `cancelled`. |
| `progress` | 0..1 optional. |
| `last_heartbeat_at` | Updated in `update_node_status`. |

**Who writes**:
- `OrchestrationHub.create_node` (orchestration_hub.py:67).
- `OrchestrationHub.update_node_status` (orchestration_hub.py:87).
- `subagent_watcher._resolve_node_for_subagent` (subagent_watcher.py:49) — finds an existing one by `external_id == agent_hash` or creates a new one.

## `orchestrator_messages`

```sql
CREATE TABLE IF NOT EXISTS orchestrator_messages (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
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
    ON orchestrator_messages (project_id, node_id, ts DESC);
```

| Column | Description |
|---|---|
| `author` | `agent` / `user` / `system`. |
| `kind` | `text` / `tool_use` / `tool_result` / `chat` / `reasoning`. See `_ingest_line` in [`claude_session_tail.py:276`](../../dreaming/services/claude_session_tail.py). |
| `delivery_status` | `delivered` (after INSERT). Reserved for retry logic. |
| `client_message_id` | for idempotency on the external client side. |

**Who writes**:
- `OrchestrationHub.append_message` (orchestration_hub.py:97).
- Called from `claude_session_tail._ingest_line` for every live line.

**Who reads**:
- `list_messages(run_id)` (orch_hub.py:112).
- `list_messages_for_node(node_id)` (orch_hub.py:119).

## `orchestrator_events`

Audit log of every event in a run. Not denormalised: `project_id` is fetched via JOIN with `orchestrator_runs` if needed.

```sql
CREATE TABLE IF NOT EXISTS orchestrator_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_or_evt_run_ts ON orchestrator_events (run_id, ts DESC);
```

`event_type` — semantic strings: `run_started`, `run_finished`, `run_failed`, `run_resumed`, `run_resume_failed`, `cascade_init`, `cascade_stage_started`, `cascade_stage_finished`, `cascade_gate`, `cascade_finished`, `message_added`. Full set in `dreaming/routes/api.py` and `dreaming/services/claude_session_tail.py`.

**payload_json** — `dict`, e.g. `{"cost_usd": 0.34}`. The parser `cascade_costs.list_cascade_costs` sums cost out of this exact field (cascade_costs.py:39–48).

## `orchestrator_stages`

```sql
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
```

Cascade stages, not denormalised.

`stage_key` — stable ID (`contract`, `design`, ...). `stage_index` — ordinal, for UI sort.
`status` ∈ {`pending`, `running`, `completed`, `failed`}.
`iteration` — repeat counter (if a gate sent the stage back).

**Who writes**: `ensure_stage` (orch_hub.py:144), `start_stage`, `finish_stage`.

## `orchestrator_gate_verdicts`

```sql
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
```

`verdict` ∈ {`approve`, `return-to-stage`, `reject`}.

**Who writes**: `record_gate_verdict` (orch_hub.py:186) — POST `/api/cascade/{run_id}/gate`.

## `orchestrator_artifacts`

```sql
CREATE TABLE IF NOT EXISTS orchestrator_artifacts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    stage_id TEXT,
    node_id TEXT,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    content_preview TEXT,
    ts TEXT NOT NULL,
    -- + dreaming via _migrate_orchestration:
    dedup_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_or_artifacts_run ON orchestrator_artifacts (run_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_or_artifacts_stage ON orchestrator_artifacts (stage_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_or_artifacts_dedup
    ON orchestrator_artifacts (run_id, dedup_hash) WHERE dedup_hash IS NOT NULL;
```

`dedup_hash` — added in migration (db.py:300). The unique partial index ensures that within a run the same `(run_id, dedup_hash)` pair exists once.

**Who writes**: `append_artifact` (orch_hub.py:210). Returns `None` on collision — endpoint `/api/cascade/{run_id}/artifact` returns `{"id": null, "deduped": true}`.

## `orchestrator_questions`

Created in `_migrate_orchestration` (db.py:316–345), not in `_SCHEMA`.

```sql
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
);
CREATE INDEX IF NOT EXISTS idx_questions_run ON orchestrator_questions(run_id, status);
CREATE INDEX IF NOT EXISTS idx_questions_pending ON orchestrator_questions(status, asked_at);
CREATE INDEX IF NOT EXISTS idx_questions_project_run_status
    ON orchestrator_questions(project_id, run_id, status);
```

Used by the AskUserQuestion flow: when Claude asks the user a question (via `tool_use` of type `AskUserQuestion`), DC creates a pending row here. The ProcessManager watchdog checks `_has_pending_question` (process_manager.py:575) — if there's a pending question, silence is not counted as silence (we wait for the user), the watchdog doesn't kill the process.

In Wave 3.9 the final API on this table isn't wired yet — it's a backfill-friendly storage for the upcoming AskUserQuestion plumbing.

## `orchestrator_tts_messages`

```sql
CREATE TABLE IF NOT EXISTS orchestrator_tts_messages (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
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
    ON orchestrator_tts_messages (project_id, ts DESC);
```

TTS (text-to-speech) messages for the voice channel. `dedup_hash` UNIQUE — won't insert again. `cleared=1` — the TTS agent has already spoken it.

In Wave 3.9 [`tts_backfill.py`](../../dreaming/services/tts_backfill.py) is a stub returning 0 (full implementation deferred).

## `ai_usage_events`

```sql
CREATE TABLE IF NOT EXISTS ai_usage_events (
    message_id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
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
    ON ai_usage_events (project_id, ts_date);
```

**Purpose**: every assistant message with usage from Claude session JSONLs. PK = `message_id` (Claude-side `message.id`). This guarantees idempotent re-ingest (a repeat INSERT OR IGNORE — no-op).

`ts_date` — the `YYYY-MM-DD` prefix of `ts`. Used in indexes for group-by-date queries.

`is_sidechain` — sub-agent message (true) vs main session (false).

`project_id` — resolved via the `cwd → project_id` map (see [`ai_usage_parser.py:91`](../../dreaming/services/ai_usage_parser.py)). If `cwd` doesn't match any `working_dir`, the event is skipped (`events_skipped++`).

**Who writes**: `ai_usage_parser._insert_events` (ai_usage_parser.py:196) — batch INSERT OR IGNORE. Runs by the `ai_usage_ingest` cron at a 5-minute interval (scheduler.py:227).

**Who reads**: `ai_usage_stats.project_summary` / `global_summary` (ai_usage_stats.py:117–149).

## `ai_usage_files`

State per JSONL file: where we stopped reading.

```sql
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
```

Composite PK `(project_id, path)` — rebuilt for multi-project support (the ALC PK was just `path`).

`byte_offset` — where we stopped last time. On the next ingest we read from there.

`is_missing=1` — file vanished. We don't delete the row, to avoid losing the offset (it might come back).

## Idempotent migrations

`_migrate_orchestration` ([`db.py:282`](../../dreaming/services/db.py)) — exactly these three actions:

1. `ALTER TABLE orchestrator_nodes ADD COLUMN stage_id TEXT` if absent.
2. `ALTER TABLE orchestrator_artifacts ADD COLUMN dedup_hash TEXT` if absent, plus `CREATE UNIQUE INDEX ... idx_or_artifacts_dedup`.
3. `CREATE TABLE IF NOT EXISTS orchestrator_questions` + 3 indexes.

Each step is wrapped in `try/except` with a warning to the log — if it fails, the app still starts (possibly with reduced functionality).

**Disciplines**:
- Don't put `NOT NULL` on ALTER TABLE'd columns (SQLite requires a default; nullable is simpler).
- Never do a PK rebuild via ALTER. If you must — write a new table, copy data, drop old, rename. See ALC discipline in [`development.md`](development.md).

## Cascade delete

Every table with `project_id` has `REFERENCES projects(id) ON DELETE CASCADE`. So `DELETE FROM projects WHERE id=N` cascades:

- `project_settings` → deleted.
- `agent_learning_sessions`, `agent_learning_rotation`, `custom_topics` → deleted.
- `orchestrator_runs`, `orchestrator_nodes`, `orchestrator_messages`, `orchestrator_questions`, `orchestrator_tts_messages` → deleted.
- `ai_usage_events`, `ai_usage_files` → deleted.

**Does NOT cascade** through `project_id`:
- `orchestrator_events` — has no `project_id` (no FK via `run_id`, MVP). Orphan events will linger.
- `orchestrator_stages`, `orchestrator_gate_verdicts`, `orchestrator_artifacts` — same. They depend on `run_id`, but the FK constraint in SQLite is without CASCADE (see db.py:165, 196).

After deleting a project, run by hand:

```sql
DELETE FROM orchestrator_events WHERE run_id NOT IN (SELECT id FROM orchestrator_runs);
DELETE FROM orchestrator_stages WHERE run_id NOT IN (SELECT id FROM orchestrator_runs);
DELETE FROM orchestrator_gate_verdicts WHERE run_id NOT IN (SELECT id FROM orchestrator_runs);
DELETE FROM orchestrator_artifacts WHERE run_id NOT IN (SELECT id FROM orchestrator_runs);
```

## Cross-references

- Schema source: [`dreaming/services/db.py`](../../dreaming/services/db.py).
- DB domain methods: see [`services.md`](services.md), Storage section.
- Which endpoint hits which table — [`api.md`](api.md).
- Backup tactics: [`deployment.md`](deployment.md).
