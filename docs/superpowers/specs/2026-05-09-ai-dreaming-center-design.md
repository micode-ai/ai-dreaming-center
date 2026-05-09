# AI Dreaming Center — Design Spec

**Date:** 2026-05-09
**Status:** Draft → spec review (2 rounds, APPROVED) → user review → writing-plans
**Revision:** rev-3 (post round-2 polish)
**Source project:** `agent-learning-center` (ALC) — single-project FastAPI dashboard for Claude CLI orchestration
**Target project:** `ai-dreaming-center` — multi-project fork at `d:\Work\micode\ai-dreaming-center`, GitHub `https://github.com/micode-ai/ai-dreaming-center`

## Goal

Build a multi-project version of ALC that manages Claude-CLI work for every project under `d:\Work\micode` (currently 11 projects). Project switching via a header dropdown. Feature parity with ALC; data scoped per project; URL-prefix-based navigation `/p/{slug}/...`.

## Foundational Decisions (Locked)

| Decision | Choice |
|---------|--------|
| Strategy | Fork ALC + add multi-project layer |
| Data model | Single SQLite DB; `project_id` column on every domain table; KV `project_settings` table for overrides |
| Scheduler | Hybrid — system-level jobs (reconcile, ai-usage-ingest, loop-watchdog) global; agent-level jobs per-project |
| URL routing | URL prefix `/p/{slug}/...`; project resolved via middleware |
| Discovery | Hybrid — DB-backed `projects` registry + "Import from `projects_root`" button that scans the filesystem |
| Feature scope | Full parity with ALC's 30+ features |
| Per-project settings | Override-with-fallback — every key can override global; missing → global default |
| Root URL `/` | Aggregated cross-project dashboard |
| UI language | i18n RU+EN (cookie-driven locale) |
| Migration approach | Wave-based (0 foundation → 5 polish) — always-shippable build between waves |

## Non-Goals

- Cross-project orchestration in v1 (one Roman per project at a time; aggregation is read-only).
- Multi-user / authentication. Single-user local tool.
- Migration of existing ALC data to dreaming-center DB. ALC keeps running independently for `scm-unity-2`; dreaming-center starts greenfield for `micode/*`.
- Test suite or linter beyond what ALC has (none).
- Docker/systemd packaging.

## Architecture

### Package layout

```
ai-dreaming-center/
  pyproject.toml           # name=ai-dreaming-center, console-script `dreaming`
  config.example.yaml
  README.md
  CLAUDE.md
  data/                    # gitignored, holds dreaming.db
  dreaming/
    main.py                # FastAPI app, lifespan, mounts, i18n filter registration
    config.py              # AppSettings (global) — pydantic-settings, prefix DC_
    models.py
    i18n/
      __init__.py          # t() lookup, load json on startup
      messages_ru.json
      messages_en.json
    middleware/
      project_resolver.py  # parses /p/{slug}/, sets request.state.project
      setup_gate.py        # 303 to /setup if no projects yet
    routes/
      root.py              # /, /projects (CRUD), /settings (global), /setup, /help
      project_dashboard.py # /p/{slug}/
      project_orchestration.py
      project_live.py
      project_rotation.py
      project_topics.py
      project_kanban.py
      project_findings.py
      project_tech_debt.py
      project_sidecar_findings.py
      project_contracts.py
      project_evolutions.py
      project_loops.py
      project_plans.py
      project_ideas.py
      project_wiki.py
      project_wiki_health.py
      project_notes.py
      project_ai_usage.py
      project_settings.py  # /p/{slug}/settings — overrides UI
      api.py               # global /api/*, project_slug from body
    services/
      db.py                # SQLite via aiosqlite + idempotent migrations
      projects.py          # CRUD + scan_projects_root() + import_from_scan()
      config_resolver.py   # get_setting(project, key) — override → global → ALC default
      project_scheduler.py # wrapper over APScheduler with per-project job IDs
      process_manager.py   # multi-project aware spawn, queue, fan-out
      orchestration_hub.py # per-project SSE channels
      harness_client.py    # per-project instance keyed by base_url override
      claude_session_tail.py
      subagent_watcher.py
      subagent_backfill.py
      model_backend.py
      jira.py
      notes.py
      agents.py
      checklist.py
      tech_debt.py
      tech_debt_stats.py
      product_ideas.py
      sidecar_findings.py
      evolutions.py
      loops.py
      plans.py
      wiki_data.py
      ai_usage_parser.py
      ai_usage_stats.py
    templates/
      base.html            # global chrome: project selector, locale toggle, scheduler pause
      _project_layout.html # nested layout with per-project nav
      ...                  # one .html per route, structured to match ALC
    static/
      app.css
      js/
  docs/
    superpowers/specs/     # this file
    smoke-tests.md         # post-wave manual checks
```

### Singletons & app.state (lifespan-bound)

Tracked verbatim against ALC's `app/main.py`:

- `db: SqliteDB` — global pool.
- `scheduler: AsyncIOScheduler` — single instance, jobs per-project tagged.
- `process_manager: ProcessManager` — single, with per-project queue.
- `orchestration_hub: OrchestrationHub` — single, with per-project SSE channels.
- `i18n: I18n` — preloaded JSON.
- `harness_client: HarnessClient | None` — replaced by lazy per-project cache `harness_clients: dict[int, HarnessClient]` keyed by `project_id`. On first access for a project, instantiate from that project's resolved `harness_*` overrides. Drop entries on project disable/delete or settings change.
- `orchestration_session_tails: dict[run_id, ClaudeSessionTail]` — keep keyed by `run_id` (already unique). Iteration "all active runs" filters by `project_id` via `orchestrator_runs` lookup.
- `orchestration_session_seen: dict[run_id, set[uuid]]` — same.
- `orchestration_subagent_watchers: dict[run_id, SubagentWatcher]` — same.
- `orchestration_subagent_tails: dict[run_id, list[ClaudeSessionTail]]` — same.
- `orchestration_finalizers: dict[run_id, asyncio.Task]` — same.
- `orchestration_tasks: dict[run_id, asyncio.Task]` — main orchestration task per run. Same keying as above.
- `orchestration_local_pm_keys: dict[run_id, str]` — maps run_id to PM key for local-mode runs. Same keying.
- `keep_awake` — Windows Modern Standby suppressor. Owned by `ProcessManager` (`pm.keep_awake`), not `app.state`; stays global, no per-project semantics.

Project resolver middleware sets `request.state.project: Project | None`. Routes never call DB to resolve slug themselves.

### Process model

Single uvicorn process. All projects share a global `max_concurrent` cap (default 2) plus per-project cap (default 1). Excess work queues in PM (in-memory FIFO with `project_id` tag).

### Server

Default port `8086` (so ALC on `8085` continues to work side-by-side during transition). Configurable via `DC_PORT` env or `port` in `config.yaml`.

## Database Schema

### New tables

#### `projects`
```sql
CREATE TABLE projects (
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
CREATE INDEX idx_projects_enabled ON projects(enabled, sort_order);
```

#### `project_settings`
```sql
CREATE TABLE project_settings (
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  key        TEXT NOT NULL,
  value      TEXT NOT NULL,           -- JSON-encoded scalar/object
  PRIMARY KEY (project_id, key)
);
```

### 14 existing ALC tables — `project_id` added

(Counted from `app/services/db.py`: 13 in `_SCHEMA` + `orchestrator_questions` from `_migrate_orchestration()`.)

| Table | project_id placement | Index |
|-------|---------------------|-------|
| `agent_learning_sessions` | new column | `(project_id, started_at DESC)` |
| `agent_learning_rotation` | new column; PK rebuilt as `(project_id, agent_name)` | — |
| `custom_topics` | new column | `(project_id, agent_name)` |
| `orchestrator_runs` | new column | `(project_id, started_at DESC)` |
| `orchestrator_nodes` | denormalized | `(project_id, run_id)` |
| `orchestrator_messages` | denormalized | `(project_id, node_id, ts)` |
| `orchestrator_events` | reachable via JOIN to `orchestrator_runs` (NOT denormalized — see Denorm Scope below) | `(run_id, ts)` |
| `orchestrator_stages` | reachable via JOIN | `(run_id)` |
| `orchestrator_gate_verdicts` | reachable via JOIN | `(stage_id)` |
| `orchestrator_artifacts` | reachable via JOIN | `(run_id)` |
| `orchestrator_questions` | denormalized (escalation job needs to filter quickly) | `(project_id, run_id, status)` |
| `orchestrator_tts_messages` | new column | `(project_id, ts DESC)` |
| `ai_usage_events` | new column | `(project_id, ts)` |
| `ai_usage_files` | PK rebuilt as `(project_id, path)` (current column name is `path`, NOT `file_path`) | — |

**Denorm scope (revised).** Only `orchestrator_nodes`, `orchestrator_messages`, `orchestrator_questions`, `orchestrator_tts_messages` get denormalized `project_id` — those drive SSE filters or per-project list queries that must avoid JOIN cost. `orchestrator_events`, `orchestrator_stages`, `orchestrator_gate_verdicts`, `orchestrator_artifacts` reach project via JOIN to `orchestrator_runs`. Reduces denorm-drift risk and migration scope.

### Settings counts (clarification)

`config.py` has ~80 settings keys (not ~40). Both global and per-project Settings UIs accordingly need pagination/grouping (groups: Database, Claude/Runner, Scheduling, Paths, Jira, Harness, AI Usage, Team-state). UI implementation is a sizable component, not a table-of-40-rows.

### Idempotent migrations

`db._migrate()` follows the pattern from ALC's `_migrate_orchestration()`: each `ALTER TABLE ADD COLUMN` is guarded by `PRAGMA table_info(...)`. **Discipline:**

1. **NOT NULL on existing rows requires a default or backfill.** SQLite `ALTER TABLE ADD COLUMN ... NOT NULL` rejects when the table has rows unless `DEFAULT` is set. Pattern: add column as `NULL`, run backfill, then (if strictness needed) rebuild table.
2. **PK changes are NOT supported by ALTER TABLE.** For `agent_learning_rotation` and `ai_usage_files` PK rebuilds, use the SQLite-recommended pattern:
   ```sql
   PRAGMA foreign_keys=OFF;
   BEGIN;
   CREATE TABLE _new_X (... new schema ...);
   INSERT INTO _new_X SELECT ..., <project_id_default> FROM X;  -- backfill in same step
   DROP TABLE X;
   ALTER TABLE _new_X RENAME TO X;
   COMMIT;
   PRAGMA foreign_keys=ON;
   ```
3. **Greenfield is the supported install path** for v1. Existing dreaming-center DBs (after first deploy) get incremental migrations under this discipline. ALC → dreaming-center data import is a non-goal.

A worked example for each migration goes in `dreaming/services/db.py` comments at the migration site.

## URL & Routing

| Level | Prefix | Pages |
|------|--------|-------|
| Global | `/` | aggregated dashboard, `/projects`, `/settings`, `/setup`, `/help`, `/static`, `/api/*` |
| Project | `/p/{slug}/` | dashboard, orchestration, live, rotation, topics, kanban, findings, tech-debt, sidecar-findings, contracts, evolutions, loops, plans, ideas, wiki, wiki-health, notes, ai-usage, settings |

Reserved (FastAPI auto): `/docs`, `/redoc`, `/openapi.json`. The old root `/notes` (ALC) does not exist; everything project-scoped.

### Project resolver middleware

Runs before route dispatch. If path starts with `/p/`, parses slug; loads project from DB (cached per-request). On unknown or `enabled=0` slug → `404` with template offering link to `/projects`. Sets `request.state.project`. Routes that need a project type-annotate it as a dependency.

### Header selector

```
┌──────────────────────────────────────────────────────────────────┐
│ AI Dreaming  [▼ mi-code-ai ●]   Dashboard | Sessions | Rotation… │
└──────────────────────────────────────────────────────────────────┘
```

Implementation: `<select onchange="...">` swaps the first segment after `/p/` and redirects. From `/p/A/tech-debt/123`, selecting `B` → `/p/B/tech-debt/123`. Stale ID in B → standard 404. Selector entries: enabled projects + `● All projects` (→ `/`) + `+ Add project` (→ `/projects?new=1`). Color dot from `projects.color`.

### API routes

Endpoints (`POST /api/session/start|finish` and similar) accept `project_slug` in JSON body; resolve project server-side. Backwards-compat: missing `project_slug` falls back to `is_default=1` project with a warning log.

### SSE channels

Per-project: `live:{slug}`, `orch:{slug}:{run_id}`. Plus global `live:*` for aggregated dashboard.

**Fan-out protocol.** ProcessManager publishes each event to both `live:{slug}` and `live:*`. Per-slug subscribers see only their slug; `live:*` subscribers see everything. This is double-fan-out at publish time, not pattern-matching at dispatch — keeps subscriber-side code identical, costs one extra `put` per event (negligible).

## i18n

- Lightweight: own minimal `i18n` module backed by two JSON files. No babel, no gettext.
- Files: `messages_ru.json`, `messages_en.json`. Flat dict, hierarchical keys (`dashboard.title`, `dashboard.metrics.success_count`).
- Jinja filter: `{{ "dashboard.title" | t }}`. Missing key → fallback ru → fallback raw key.
- Locale: cookie `dc_locale` (`ru`/`en`); switcher next to project selector. Default `ru`.
- Pluralization: `n_sessions.one|few|many|other`. Russian rules per CLDR (NOT naive 1 / 2-4 / 5+):
  - `one`: `n % 10 == 1 && n % 100 != 11` (1, 21, 31, 101 …)
  - `few`: `n % 10 in {2,3,4} && n % 100 not in {12,13,14}` (2-4, 22-24, 32-34 …)
  - `many`: `n % 10 == 0 || n % 10 in {5..9} || n % 100 in {11..14}` (0, 5-20, 25-30 …)
  - `other`: fractional only (not used for counts)
- Out of scope: log lines, agent-name labels read from `.claude/agents/`, markdown content of notes/tech-debt. Only chrome (UI shell, buttons, headings, errors).
- Pre-commit script `scripts/check_i18n.py` verifies key parity between `ru.json` and `en.json`.

## Settings

### Global `/settings`
Table of ~80 keys (grouped) (model, claude_path, default crons, runner profile, jira, harness, ai-usage, paths). Each: current value, type, description. Save → writes to `config.yaml` and reloads.

### Project `/p/{slug}/settings`
Same ~80 keys (grouped), three states each:
- `[ inherit ]` — fallback to global
- `[ override ]` — project-specific value
- `[ unset ]` (optional keys only) — explicit empty

Saves to `project_settings` (or deletes the row when reverted to inherit).

### `config_resolver.get_setting(project, key)`

```python
def get_setting(project, key, default=None):
    if project:
        v = project_settings.get(project.id, key)
        if v is not None: return v
    v = global_settings.get(key)
    if v is not None: return v
    return default
```

Cached per-request to avoid N+1 reads during page render.

## Scheduler

ALC has 14 jobs total: 9 cron via `_add_cron_job` + 5 interval jobs. dreaming-center keeps the same set, splits between global and per-project as below.

### Global jobs (interval, always on)
- `reconcile_stale_sessions` — every 5 min. Iterates PM running, closes orphans. Now takes `(project_id, agent_name)` tuples (since two projects may share an agent name like `frontend-architect`).
- `reconcile_stale_orchestration_runs` — every 5 min. Marks runs as `stale`/`completed` based on PID and last activity. Runs cross-project; uses `orchestrator_runs.project_id` to attribute.
- `_questions_escalation` — every 1 min. Re-notifies open `orchestrator_questions` past their reminder threshold; auto-answers expired ones. Picks project from `orchestrator_questions.project_id` and routes the auto-answer back to the correct project's PM/run.
- `loop_watchdog` — every `loop_watchdog_interval_minutes` (global). For each enabled project: scan loops dir.
- `ai_usage_ingest` — every `ai_usage_scan_interval_minutes`. Parses `~/.claude/projects/*.jsonl`, maps each entry's `cwd` to a project (or `__unassigned__`).

### Per-project jobs
Job ID format: `{kind}_{slug}` (stable, dedupe-friendly).

Kinds (all 9 cron-based jobs from ALC): `nightly_learning`, `weekly_tech_debt_scan`, `weekly_product_ideas_scan`, `weekly_timur_duty`, `weekly_wiki_lint`, `monthly_deep_audit`, `daily_bootstrap`, `weekly_evolve_apply`, `daily_plans_cleanup`. Up to 9 × N projects.

Both `_add_cron_job` (cron) and direct `scheduler.add_job` (interval) paths are touched during rewriting. Pattern in `project_scheduler.py`: `add_project_job(kind, project, ...)` dispatches to the right underlying call.

Lifecycle:
- Startup → register jobs for every `enabled=1` project.
- Project added/enabled/disabled/deleted → unregister + register.
- Cron expression edited in `/p/{slug}/settings` → reschedule.

### Pause
- Global: existing scheduler pause (pauses all).
- Per-project: `paused=true` in `project_settings`. Job lifecycle calls `scheduler.pause_job(job_id)`.

### Conflict warning
Validation as in ALC. Additional UI warning: if multiple projects share `nightly_learning` cron + global `max_concurrent=1`, second will queue.

## Process Manager

### Concurrency

| Param | Level | Behavior |
|-------|-------|----------|
| `max_concurrent` | global | Hard cap on simultaneous claude/codex processes across all projects. Default 2. |
| `max_concurrent_per_project` | global, override-able | Default 1. `0` disables per-project cap. |
| `wait_between_sec` | global | Pause between launches in a wave. |

Excess work queued in PM (in-memory FIFO, tagged with `project_id`). Queue visible on aggregated dashboard and `/p/{slug}/` ("Очередь: 2 задания").

### `start_session(project, agent_name, ...)` flow
1. Resolve effective config via `config_resolver` (claude_path, model, working_dir, timeout_minutes — any may be overridden).
2. `running[f"{project.slug}:{agent_name}"]`.
3. Pre-create DB row with `project_id = project.id`.
4. `cwd = project.working_dir` (different per project — critical, otherwise self-study runs in wrong tree).
5. Spawn → ring buffer → SSE fan-out on `live:{slug}` and `live:*`.

### `start_command(project, command_name, prompt, ...)`
Same flow; key `cmd:{slug}:{command_name}`.

### Watchdog
Reads `timeout_minutes` at spawn time (resolved per-project). Static for the lifetime of one process.

### Reconcile
For each `running`: if PID is gone → close DB row; respect 2-min grace window for async finish from `/self-study` (matches ALC behavior). API takes `(project_id, agent_name)` tuples — agent names like `frontend-architect` may collide across projects, so `agent_name`-only filter is unsafe. **Note:** this changes `ProcessManager.reconcile_stale_sessions(active_agents)` signature from agent-name-keyed to tuple-keyed. Fork-internal break only; ALC remains untouched.

### Path safety
Before spawn:
1. `project.working_dir` exists.
2. Not parent of dreaming-center itself.
3. Resolves under `projects_root` (no symlink-out). Optionally allow paths outside via explicit project flag `allow_outside_root`.

Slash-commands run with `--dangerously-skip-permissions`, so a wrong `cwd` could mutate the wrong tree. On invalid → row status `error` with human-readable message; never spawn.

### One-Roman-per-project enforcement
Spec target: at most one orchestration run with `status='running'` per `project_id`. Mechanism:

- `POST /p/{slug}/api/orchestration/start` (and the cascade variants) execute a guard:
  ```sql
  SELECT COUNT(*) FROM orchestrator_runs WHERE project_id=? AND status='running'
  ```
  Non-zero → respond `409 Conflict` with the existing `run_id` so UI can offer "View existing run".
- The same check applies to `start_command` for command kinds that produce orchestration runs (`/cascade-task`, `/cascade-contract`, `/team-task`, `/team-fullstack`).
- Self-study and other non-orchestration commands are NOT subject to this lock; they're capped only by `max_concurrent` / `max_concurrent_per_project`.

## Wave-Based Migration

Each wave is independently shippable. Last commit of each wave gets git tag `wave-N`.

### Wave 0 — Foundation (no UI value, scaffolding)
- Scaffold `pyproject.toml`, `dreaming/main.py`, `config.py`, lifespan, base layout with empty selector.
- `services/db.py` — copy + new `projects`, `project_settings`, `project_id` on existing 14 tables (incl. `orchestrator_questions`), idempotent migrations using the SQLite PK-rebuild pattern.
- `services/projects.py` — CRUD, `scan_projects_root()`, `import_from_scan(slugs)`.
- `middleware/project_resolver.py`, `middleware/setup_gate.py` (303 → `/setup` when `projects` empty).
- `services/config_resolver.py`, `services/i18n.py`, empty `messages_ru.json`, `t()` filter.
- Routes: `/setup` (multi-project wizard — substantial new component, see below), `/projects` (list + CRUD), global `/settings`, `/health`. `/` redirects to `/projects` (placeholder).
- Stubbed-only files (created Wave 0 to keep import surface complete, populated later): `claude_session_tail.py`, `subagent_watcher.py`, `subagent_backfill.py`, `orchestration_hub.py`. Each contains a no-op class with the public API of the ALC counterpart so that imports don't break.

**Setup wizard (Wave 0 sub-tasks).** Unlike ALC's 4-field setup (`app/routes/setup.py` ~60 LOC), the dreaming-center wizard is a multi-step UI:
1. Step 1 — global config: `claude_path`, runner profile, default `model`, optional Jira creds.
2. Step 2 — choose `projects_root` (default `d:\Work\micode`).
3. Step 3 — scanner output: list of detected directories with checkboxes (enabled/disabled), editable slug, editable label, "is default" radio. Server-side service `scan_projects_root()` enumerates dirs, suggests slugs (basename, with `-2`, `-3` suffix on collision), detects presence of `.claude/` for an info badge.
4. Submit → batch insert into `projects`; commit `config.yaml`; redirect to `/`.

**Acceptance:** Setup wizard scans `d:\Work\micode`, imports the 11 projects, registers them. `/projects` lists. Server boots cleanly. Re-running setup is idempotent (don't duplicate slugs).

### Wave 1 — Core (daily-use surface)
Routes under `/p/{slug}/`: dashboard, live (+ kill), rotation, topics, kanban, notes, settings (overrides UI), work-routing widget (engine selection: claude/codex/continue per `model_backend_profile` override). `/api/session/start|finish` accept `project_slug`. ProcessManager: `start_session(project, agent)`. Scheduler: `nightly_learning_{slug}` cron + global `reconcile_stale_sessions` and `_questions_escalation` interval.

External-artifact audit: grep `agent-team-starter-kit/templates/` for `localhost:8085` and `/api/`; inventory all touched files; update each to use `$DREAMING_API_URL` and pass `project_slug`.

**Acceptance:** `/self-study` runs from UI and API; live log streams; row appears on dashboard; nightly cron honors per-project schedule; per-project pause works; work-routing engine selection respects per-project override.

### Wave 2 — Pipelines
Findings, tech-debt, sidecar-findings, contracts, ideas, wiki, wiki-health. Per-project crons: `weekly_tech_debt_scan_{slug}`, `weekly_product_ideas_scan_{slug}`, `weekly_timur_duty_{slug}`, `weekly_wiki_lint_{slug}`, `monthly_deep_audit_{slug}`, `daily_bootstrap_{slug}`. Jira creds overridable per-project (different `jira_project_key` per micode project).

**Acceptance:** Each project has its own tech-debt list, scan crons, ideas → Jira with right project key. Pipelines isolated.

### Wave 3 — Orchestration
Implementation (real, not stubs) of: `OrchestrationHub` (per-project channels), `claude_session_tail`, `subagent_watcher`, `subagent_backfill`. Routes:
- `/p/{slug}/orchestration` — Roman live graph, per-node chat, slash-command picker, screenshot paste, resume by `run_id`.
- All `/api/orchestration/*`, `/api/cascade/*` endpoints (~25) — back-resolve `project_id` from `run_id` for routing.
- `harness_client` lazy per-project cache from `harness_*` overrides.
- Cascade pipelines (`/cascade-task`, `/cascade-contract`); cascade SKILL.md templates updated to use `$DREAMING_API_URL`.
- One-Roman-per-project lock (409 on concurrent start; UI offers "View existing run").
- All `app.state.orchestration_*` dicts keyed by run_id stay; iteration filters by project as needed.

**Concurrency:** one Roman per project simultaneously, enforced via `orchestrator_runs` query. Aggregated dashboard shows `Active runs` list across projects.

**Acceptance:** Roman in project A doesn't block Roman in project B. Second start in same project returns 409 with existing run_id. SSE channels don't cross. JSONL session-tail correctly attributes sub-agent events.

### Wave 4 — Team-state, AI Usage, Cascade Costs
- `/p/{slug}/evolutions`, `/p/{slug}/loops` (incl. loop templates seed running per-project on lifespan), `/p/{slug}/plans`, `/p/{slug}/ai-usage`, `/p/{slug}/cascade-costs` (separate dashboard from AI Usage; reads orchestrator events for per-cascade cost roll-up).
- Per-project crons: `weekly_evolve_apply_{slug}`, `daily_plans_cleanup_{slug}`. Global intervals: `loop_watchdog`, `ai_usage_ingest`, `reconcile_stale_orchestration_runs`.
- AI-Usage parser maps each JSONL file to a project via `cwd` ↔ `working_dir`; unmatched go to `__unassigned__` bucket (visible on root `/ai-usage`).

**Acceptance:** AI usage attributed correctly. Loops/plans/evolutions per-project. Cascade Costs dashboard renders correctly per-project. Loop templates seed runs per-project.

### Wave 5 — Aggregated dashboard & polish
Aggregated `/`: cards per project (week sessions / runs / TD count), top-line metrics, AI-Usage summary. `messages_en.json` filled. README, CLAUDE.md, screenshots. Push to GitHub.

**Acceptance:** Public deploy story works: clone → install → setup wizard → use.

## External Artifacts (Slash-Commands & Skills)

The full surface of artifacts that hard-code `localhost:8085` or `/api/...` paths and need updating:

### Env-var contract
dreaming-center exports two env vars to every spawned subprocess:
- `DREAMING_PROJECT_SLUG` — slug of the spawning project.
- `DREAMING_API_URL` — base URL (default `http://localhost:8086`).

Slash-commands and skills read these.

### Slash commands (`.claude/commands/*.md` and `agent-team-starter-kit/templates/commands/`)
- `self-study.md`, `bootstrap-module.md`, `timur-weekly-duty.md`, `wiki-lint.md`, `wiki-deep-audit.md`, `tech-debt-work.md`, `product-idea-triage.md`, `product-idea-work.md`, `team-backend.md`, `team-frontend.md`, `team-fullstack.md`, `team-task.md`, `team-testing.md`, `new-task.md`, `cascade-task.md`-equivalent, etc.
- All callers of `POST /api/session/start|finish` add `project_slug` to body.

### Skills (`agent-team-starter-kit/templates/skills/`)
- `cascade-task/SKILL.md` — calls `/api/cascade/{run_id}/gate`, `/api/cascade/{run_id}/finish`. Must use `$DREAMING_API_URL`. project_slug not strictly required (run_id resolves project), but pass for log clarity.
- `cascade-contract/SKILL.md` — same.
- `evolve-agent/SKILL.md`, `handoff/SKILL.md`, `new-feature/SKILL.md`, etc. — audit each for hard-coded ALC URL.

### REST API surface (server side)
All `/api/cascade/*`, `/api/orchestration/*`, `/api/session/*` endpoints (~25 in `app/routes/orchestration.py`) become multi-tenant by **back-resolving project from `run_id`** (since `run_id` is globally unique) rather than requiring `project_slug` in body. Endpoints that don't have a `run_id` (e.g. `/api/session/start` for new sessions) take `project_slug` in body and resolve via `projects.slug`. Backwards-compat: missing `project_slug` AND no resolvable `run_id` → fall back to default project + log warning.

### Audit step
Wave 1 includes a one-time grep across the `agent-team-starter-kit/templates/` tree for `localhost:8085`, `/api/session`, `/api/cascade`, `/api/orchestration`. The full list of touched files is captured in a Wave 1 PR description.

### Untouched
`.claude/agents/_context/`, lessons, agent profile markdown — read-only from dreaming-center side, no changes.

## Testing

ALC has no test suite (per CLAUDE.md: "no test suite, linter, or formatter; do not invent commands for them"). Dreaming-center inherits this convention. Smoke tests are documented in `docs/smoke-tests.md` and run manually after waves 1, 3, 5:

1. Setup wizard from empty → 3 projects imported, registry populated.
2. `POST /api/session/start` with `project_slug` → session row created.
3. Selector switch between two projects keeps data isolated.
4. `nightly_learning_{slug}` fires for one project while others paused.
5. Aggregated `/` shows correct sums.

## Deployment

- Local: `python -m uvicorn dreaming.main:app --port 8086 [--reload]`. No systemd/docker. User-local tool.
- Windows quirk: `shutil.which(claude_path)` resolves `claude.cmd` (preserved from ALC).
- Env vars: `DC_*` prefix (analogous to ALC `ALC_*`). Pydantic-settings auto-binds. Secrets (`DC_JIRA_API_TOKEN`) belong in env, not `config.yaml`.
- Git repo: `https://github.com/micode-ai/ai-dreaming-center`. License: MIT (assumed; confirm during finalization).

## Error Handling & Edge Cases

- **Slug conflict.** Scanner finds two paths with the same basename → suffix `-2`, `-3`. UI: "slug auto-suffixed, edit if needed".
- **Project deletion.** `DELETE /projects/{id}` → CASCADE removes all data. UI requires the user to retype the slug for confirmation.
- **Disable project.** `enabled=0` → crons paused, selector hides; `/p/{slug}/` accessible read-only with banner.
- **Default project.** Exactly one project → it's default. Zero projects → `/` redirects to `/setup`. >1 with no default → aggregated `/` works (no fallback needed).
- **Empty `working_dir`.** Spawn fails fast with human-readable error in DB and UI.
- **Missing `.claude/agents/`.** Rotation page shows empty state + link to starter-kit setup. Doesn't block project registration.
- **Orphan session.** CASCADE prevents this normally; reconcile job marks any `orphan` status defensively.
- **Concurrent settings save.** Last-write-wins. Single-user local tool, no optimistic locking.
- **i18n missing key.** Returns the key as a string. Pre-deploy `scripts/check_i18n.py` fails on key divergence.

## Open Questions

- License: MIT vs internal? Assumed MIT based on `micode-ai` GitHub org being public; confirm before push.
- Aggregated `/ai-usage` — should `__unassigned__` JSONLs be hideable / re-mappable manually? Defer to post-Wave-4 feedback.
- Per-project `claude_path` — useful in theory (different projects could pin different Claude versions), but unlikely in practice. Keep overridable for cheapness.

## Appendix: Inventory of Source ALC Features

(For migration tracking — ensures no feature is missed during waves.)

**Core / live work**
- Dashboard (week stats, recent sessions, active runs, scheduler status, pause/resume) → Wave 1
- Orchestration (Roman graph, per-node chat, slash picker, screenshot paste, resume) → Wave 3
- Live Log (SSE stream, kill) → Wave 1
- Rotation (table, inline tier/enabled, who's-next preview) → Wave 1
- Kanban / Topics (custom_topics injection) → Wave 1
- AI Usage (token/cost trends) → Wave 4

**Scanners and pipelines**
- Tech Debt dashboard + per-release + module filters + per-TD detail → Wave 2
- Findings list + bulk actions + localStorage filters → Wave 2
- Product Ideas board + weekly cron + Jira Epic + git branch + roman decomposition → Wave 2
- Sidecar Findings + add-to-TD batch → Wave 2
- Contracts (module/page) → Wave 2

**Knowledge base**
- Notes (`/p/{slug}/notes`) → Wave 1
- Wiki bootstrap UI → Wave 2
- Wiki Health + monthly deep-audit cron → Wave 2

**Team-state**
- Evolutions (`_context/` overrides + conflict gate) → Wave 4
- Reflex Loops (create/resume/stop/clean + watchdog) → Wave 4
- Plans (Roman plan files + marker progress) → Wave 4

**System**
- Help (`/help` single-page) → Wave 0/5
- Settings (full configuration UI, ~80 keys with override states) → Wave 0 (global skeleton) + Wave 1 (per-project overrides UI)
- Setup Wizard (multi-project) → Wave 0
- Scheduler (14 jobs total: 9 cron per-project + 5 global interval) → distributed across waves; control plane Wave 0
- Work Routing (`/work/route`, `/work/run` engine selection) → Wave 1
- Cascade Costs (`/cascade-costs` dashboard) → Wave 4
- Loop Templates (with lifespan seed per-project) → Wave 4
- REST API (incl. `/api/cascade/*`, `/api/orchestration/*`, ~25 endpoints) → Wave 1 baseline; orchestration-specific endpoints in Wave 3

**Aggregated**
- Cross-project root dashboard → Wave 5
- i18n RU + EN → Wave 0 (infra) + Wave 5 (full EN translation, key-parity check script)
