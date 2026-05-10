# AI Dreaming Center architecture

This document describes the overall layout of the application: which processes run, which singletons live on `app.state`, in what order middleware fires, how startup/shutdown happens, and where each subsystem reaches into others.

## Contents

- [High-level diagram](#high-level-diagram)
- [Process model](#process-model)
- [Lifespan](#lifespan)
- [Middleware](#middleware)
- [Singletons on `app.state`](#singletons-on-appstate)
- [URL routing and project resolver](#url-routing-and-project-resolver)
- [Concurrency model](#concurrency-model)
- [File layout](#file-layout)
- [Cross-references](#cross-references)

## High-level diagram

```
+--------------------+         +------------------------+
|    Browser         |  HTTP   |   uvicorn (asyncio)    |
|  htmx + Tailwind   +---------+    FastAPI app         |
|  SSE for /live     |         |                        |
+--------------------+         +-----------+------------+
                                           |
                                           v
                            +---------------------------+
                            |   Middleware chain        |
                            |   1. setup_gate (OUTER)   |
                            |   2. project_resolver     |
                            +-------------+-------------+
                                          |
                                          v
                              +-----------+-----------+
                              |   Routers (19 total)  |
                              |   /, /setup, /api,    |
                              |   /p/{slug}/*         |
                              +-----------+-----------+
                                          |
            +-----------------------------+-----------------------------+
            |                             |                             |
            v                             v                             v
+-----------+-----------+    +------------+--------------+   +----------+----------+
|   Service layer       |    |   ProcessManager          |   |   APScheduler      |
|   (db, projects,      |    |   spawn(claude CLI)       |   |   AsyncIOScheduler |
|   resolver, hubs,     |    |   ring buffer + SSE       |   |   nightly + 5min   |
|   parsers)            |    |   KeepAwake refcount      |   |   reconcile + ai-  |
+-----------+-----------+    +------------+--------------+   |   usage + per-prj  |
            |                             |                  +----------+---------+
            v                             v                             |
+-----------+----------------------------+-----------+                  |
|                     SQLite (WAL)                   |  <---------------+
|  data/dreaming.db — 16 tables + idemp. migrations |
+----------------------------------------------------+
```

Arrows go in one direction: routes -> services -> db. Services cross-reference each other only through explicit dependency injection (constructor or explicit arguments).

## Process model

One process, `python -m uvicorn dreaming.main:app --port 8086` (see [`pyproject.toml`](../../pyproject.toml) — dependencies, and [`README.md`](../../README.md) — quickstart). Inside it:

- **asyncio loop** — the only one, all IO (HTTP, SQLite, subprocess, scheduler) sits on it.
- **One persistent SQLite connection** in WAL mode (see [`dreaming/services/db.py`](../../dreaming/services/db.py) lines 269–280: `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON` are set BEFORE `executescript(_SCHEMA)`).
- **Subprocesses** of the Claude CLI, spawned via `asyncio.create_subprocess_exec` — limit `STDOUT_BUFFER_LIMIT = 16 MB` (process_manager.py:28), because the stream-json output from Claude can ship very large assistant blocks.
- **APScheduler** in `AsyncIOScheduler` mode — runs on the same loop, no separate thread/process is created (see [`dreaming/services/scheduler.py`](../../dreaming/services/scheduler.py) `build_scheduler`, line 219).

Concurrency is bounded by:
- `max_concurrent` (default 2) — how many parallel Claude sessions ProcessManager keeps (process_manager.py:92).
- Per-project: composite key `'{slug}:{agent}'` or `'cmd:{slug}:{name}'` — see process_manager.py:91.

The single-process design is deliberate: Roman is a root, long-lived process, and we don't want to fork DB state across workers. To scale — run a second instance with a different `port`/`db_path`, not multiple workers of one uvicorn.

## Lifespan

[`dreaming/main.py`](../../dreaming/main.py) defines `@asynccontextmanager async def lifespan(app)` — strictly ordered:

1. `app.state.settings = load_settings()` — Pydantic `AppSettings.load()` reads [`config.yaml`](../../config.example.yaml) + env vars `DC_*`.
2. `app.state.db = SqliteDB(settings.db_path)` + `await db.connect()` — creates the directory, opens the connection, sets PRAGMAs, runs `_SCHEMA + _migrate_orchestration`.
3. `app.state.projects = ProjectsService(db)` — registry service.
4. `app.state.templates = Jinja2Templates("dreaming/templates")` — Jinja2.
5. `app.state.i18n = I18n(Path("dreaming/i18n"))` — loads `messages_ru.json` + `messages_en.json`.
6. Bind the `t()` filter into the Jinja env: `templates.env.filters["t"] = _t` (main.py:40).
7. `app.state.process_manager = ProcessManager(settings, db, projects)`.
8. `app.state.orchestration_hub = OrchestrationHub(db, projects)`.
9. `app.state.harness_clients = HarnessClientCache()`.
10. `app.state.scheduler = build_scheduler(app.state)` + `scheduler.start()`.
11. For every enabled project: `register_project_jobs(scheduler, app.state, proj)`.
12. `app.state.resolver_factory = get_resolver` — a factory; ConfigResolver is built PER REQUEST (see main.py:69).
13. `yield` — the application runs.
14. On shutdown: `scheduler.shutdown(wait=False)` + `await db.close()` (in `finally:` — runs even on exception).

Lifespan matters because **routes must not instantiate services again**: always `request.app.state.<name>`.

## Middleware

Registered in [`main.py`](../../dreaming/main.py) lines 65–66:

```python
app.middleware("http")(project_resolver_middleware)   # inner
app.middleware("http")(setup_gate_middleware)         # outer
```

In Starlette, middleware registered last runs FIRST on the request path. So:

```
Request --> setup_gate (OUTER) --> project_resolver (INNER) --> route
```

Logic:

1. **`setup_gate`** ([`dreaming/middleware/setup_gate.py`](../../dreaming/middleware/setup_gate.py)) — if the `projects` table is empty AND the path is not in `_BYPASS_PREFIXES = ("/setup", "/static", "/health", "/api", "/docs", "/redoc", "/openapi")`, returns `RedirectResponse("/setup", 303)`. This is the first-run wizard gate.

2. **`project_resolver`** ([`dreaming/middleware/project_resolver.py`](../../dreaming/middleware/project_resolver.py)) — if the path starts with `/p/<slug>/`, parses `<slug>`, looks up the project via `projects.get_by_slug(slug)`. If not found OR `enabled=False` — returns 404 with the `project_not_found.html` template. If found — writes `request.state.project = project`, and downstream routes read it from there (instead of repeating the DB lookup).

The order matters: setup_gate first so that /p/* requests against an empty DB redirect straight to /setup, instead of trying to resolve a slug against an empty table.

## Singletons on `app.state`

| Attribute | Type | Where created |
|--------|------|------|
| `settings` | `AppSettings` (Pydantic) | main.py:30 |
| `db` | `SqliteDB` | main.py:31 |
| `projects` | `ProjectsService` | main.py:33 |
| `templates` | `Jinja2Templates` | main.py:34 |
| `i18n` | `I18n` | main.py:35 |
| `process_manager` | `ProcessManager` | main.py:41 |
| `orchestration_hub` | `OrchestrationHub` | main.py:43 |
| `harness_clients` | `HarnessClientCache` | main.py:44 |
| `scheduler` | `AsyncIOScheduler` | main.py:45 |
| `resolver_factory` | `Callable[[Request], ConfigResolver]` | main.py:50 |
| `orchestration_tails` | `dict[run_id, Task]` | created lazily in [`project_orchestration.py:118`](../../dreaming/routes/project_orchestration.py) |
| `orchestration_watchers` | `dict[run_id, Task]` | created lazily in [`project_orchestration.py:136`](../../dreaming/routes/project_orchestration.py) |

Remember: `ConfigResolver` is NOT a singleton, it's created on every request via `resolver_factory(request)`. This is so that the per-request cache `_cache: dict[int, dict]` does not accumulate.

## URL routing and project resolver

Router registry — in `main.py` lines 74–80:

```
/        ->  root_router            (dashboard, /health, /locale, /ai-usage)
/setup   ->  setup_router           (wizard)
/projects ->  projects_router       (CRUD over projects)
/settings ->  settings_router       (global settings)
/api/*   ->  api_router             (sessions, orchestration, cascade)
/p/*     ->  project_router         (aggregator over 19 sub-routers /p/{slug}/*)
/static  ->  StaticFiles            (CSS/JS)
```

Every `/p/{slug}/...` route gets its `project` via `request.state.project` (set earlier by `project_resolver_middleware`). If routes pulled the slug themselves it would be N+1 — middleware saves the lookup.

Inside `project_router`:

- See [`dreaming/routes/project_router.py`](../../dreaming/routes/project_router.py) — it only aggregates the 19 sub-routers via `include_router`.
- Detailed route inventory — in [`routes.md`](routes.md).

## Concurrency model

ProcessManager keeps a dictionary `running: dict[str, RunningSession]` keyed by:

- `"{project_slug}:{agent_name}"` — for `start_session` (self-study).
- `"cmd:{project_slug}:{command_name}"` — for `start_command` (slash-commands and raw).

On spawn:
1. `start_session/start_command` checks `if key in self.running: raise`. Re-checks `len(self.running) >= max_concurrent`.
2. Pre-creates a DB row via `db.create_session(project_id, agent_name, model)` — so we have an ID before the spawn (process_manager.py:142).
3. `asyncio.create_subprocess_exec(claude, "-p", prompt, ...)` with stdout pipe, `stderr=STDOUT`, 16MB limit.
4. Creates a `_reader_task` (reads stdout, fans out to subscribers' queues — that's SSE) and a `_watchdog_task` (kills on `timeout_minutes` of silence).
5. `keep_awake.acquire()` — bumps Windows ExecutionState so the system doesn't drop into Modern Standby.

On termination:
- `_read_stdout` reaches EOF, sends sentinel `None` to all subscribers, calls `_cleanup`.
- `_cleanup` removes the session from `running`, calls `keep_awake.release()`, and (unless `cmd:*`) runs `db.reconcile_stale_sessions()` to close orphaned DB rows whose process died.
- The watchdog separately: every `min(60, timeout_minutes*60)` seconds checks `time.time() - last_stdout_at`. If there's a pending question (a row in `orchestrator_questions` with status `pending`) — resets the counter (a valid waiting state for user response).

The reconcile job at a 5-minute interval (scheduler.py:223) gathers `(project_id, agent_name)` pairs from the in-memory `pm.running`, hands them to `pm.reconcile_stale_sessions(active_pairs)`. The server doesn't know that Claude died on its own — `_cleanup` will close the row.

Additionally: on `start_session` via [`project_orchestration.py:84`](../../dreaming/routes/project_orchestration.py) we spawn:
- `ClaudeSessionTail` — a task that reads Claude's jsonl file and pours it into `orchestrator_messages`.
- `SubagentWatcher` — a task that watches for `subagents/agent-*.meta.json` and spawns a child tail per sub-agent.

These tasks live in `app.state.orchestration_tails` / `app.state.orchestration_watchers` (per run).

## File layout

```
dreaming/
+-- main.py                    # FastAPI app, lifespan, middleware, router mount
+-- config.py                  # AppSettings (92 fields) + SETTINGS_GROUPS (13 groups)
+-- middleware/
|   +-- setup_gate.py          # /setup redirect when DB is empty
|   +-- project_resolver.py    # /p/{slug}/ -> request.state.project
+-- routes/
|   +-- root.py                # / + /health + /locale + /ai-usage
|   +-- setup.py               # /setup wizard
|   +-- projects.py            # /projects CRUD (toggle, delete, import)
|   +-- settings.py            # /settings global form
|   +-- api.py                 # /api/* (sessions + orchestration + cascade)
|   +-- project_router.py      # aggregator for /p/{slug}/* sub-routers
|   +-- project_dashboard.py   # /p/{slug}/
|   +-- project_live.py        # /p/{slug}/live + SSE stream + kill
|   +-- project_rotation.py    # /p/{slug}/rotation
|   +-- project_settings.py    # /p/{slug}/settings (per-project overrides)
|   +-- project_orchestration.py
|   +-- project_topics.py      # weekly-learning-checklist
|   +-- project_kanban.py      # custom_topics CRUD
|   +-- project_notes.py       # learning-notes browser
|   +-- project_findings.py    # tech-debt list+detail+close+delete
|   +-- project_tech_debt.py   # tech-debt aggregate
|   +-- project_ideas.py       # product ideas + Jira
|   +-- project_wiki.py        # wiki status + bootstrap button
|   +-- project_ai_usage.py    # per-project token usage
|   +-- project_evolutions.py
|   +-- project_loops.py
|   +-- project_plans.py
|   +-- project_cascade_costs.py
|   +-- project_contracts.py
|   +-- project_sidecar_findings.py
+-- services/
|   +-- db.py                  # SqliteDB + _SCHEMA + _migrate_orchestration + ~30 domain methods
|   +-- projects.py            # ProjectsService + scan_projects_root
|   +-- config_resolver.py     # ConfigResolver (override-with-fallback)
|   +-- process_manager.py     # claude CLI spawn / SSE / watchdog / reconcile
|   +-- keep_awake.py          # Windows SetThreadExecutionState refcount
|   +-- scheduler.py           # _PER_PROJECT_JOBS, build_scheduler
|   +-- orchestration_hub.py   # runs/nodes/messages/stages/verdicts/artifacts
|   +-- claude_session_tail.py # JSONL tail-watcher
|   +-- subagent_watcher.py    # subagents/ folder watcher
|   +-- subagent_backfill.py   # offline replay
|   +-- harness_client.py      # HTTP/SSE harness adapter
|   +-- cascade_stage_detect.py # heuristic agent_name -> stage
|   +-- tts_backfill.py        # stub Wave 3.9
|   +-- ai_usage_parser.py     # JSONL -> ai_usage_events
|   +-- ai_usage_stats.py      # aggregate dashboards
|   +-- tech_debt.py           # parser + close/delete
|   +-- product_ideas.py       # parser
|   +-- contracts.py           # parser
|   +-- sidecar_findings.py    # JSON parser
|   +-- wiki_data.py           # WikiStatus
|   +-- evolutions.py          # markdown parser
|   +-- loops.py               # markdown parser
|   +-- plans.py               # markdown parser + checkbox progress
|   +-- cascade_costs.py       # cost roll-up
|   +-- notes.py               # learning-notes lister + safe reader
|   +-- checklist.py           # weekly checklist parser
|   +-- agents.py              # discover .claude/agents/
|   +-- jira.py                # create_task for Jira REST API v3
|   +-- i18n.py                # I18n + russian_plural / english_plural
+-- templates/
|   +-- base.html
|   +-- _navbar.html
|   +-- _project_layout.html
|   +-- index_dashboard.html
|   +-- project_*.html         # ~20 pages
+-- i18n/
|   +-- messages_ru.json
|   +-- messages_en.json
+-- static/
    +-- app.css                # additional CSS over the Tailwind CDN
```

Repo root:

```
+-- pyproject.toml             # editable install, deps
+-- config.yaml                # working config (created by the wizard)
+-- config.example.yaml        # template
+-- data/dreaming.db           # SQLite (created on connect())
+-- scripts/                   # smoke scenarios (no test framework, see development.md)
+-- docs/                      # this documentation
```

## Cross-references

- More on the DB: [`schema.md`](schema.md).
- Each service in detail: [`services.md`](services.md).
- Each route with its response code: [`api.md`](api.md), [`routes.md`](routes.md).
- Settings and override chain: [`configuration.md`](configuration.md), [`features/settings.md`](features/settings.md).
- Deployment, persistent run and backup: [`deployment.md`](deployment.md).
- About i18n: [`features/i18n.md`](features/i18n.md).
- Multi-project resolver and the setup wizard: [`features/multi-project.md`](features/multi-project.md).
