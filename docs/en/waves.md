# Waves history

History of AI Dreaming Center development: what was done in each wave, the git tag, what was deferred.

## Contents

- [Wave 0 — Foundation](#wave-0--foundation)
- [Wave 1 — Self-study core](#wave-1--self-study-core)
- [Wave 2 — Pipeline pages](#wave-2--pipeline-pages)
- [Wave 2.5 — Tech-debt + Jira + Wiki bootstrap](#wave-25--tech-debt--jira--wiki-bootstrap)
- [Wave 3 lean — OrchestrationHub](#wave-3-lean--orchestrationhub)
- [Wave 3.6 — claude_session_tail / subagent_watcher / backfill](#wave-36--claude_session_tail--subagent_watcher--backfill)
- [Wave 3.7 — orchestration spawns claude](#wave-37--orchestration-spawns-claude)
- [Wave 3.8 — cascade pipelines API](#wave-38--cascade-pipelines-api)
- [Wave 3.9 (Wave 3 full) — contracts + sidecar + tts stub](#wave-39-wave-3-full--contracts--sidecar--tts-stub)
- [Wave 4 lite — AI Usage analytics](#wave-4-lite--ai-usage-analytics)
- [Wave 4 full — evolutions / loops / plans / cascade-costs](#wave-4-full--evolutions--loops--plans--cascade-costs)
- [Wave 5 — aggregated dashboard](#wave-5--aggregated-dashboard)
- [Not implemented yet](#not-implemented-yet)

## Wave 0 — Foundation

**Tag**: `wave-0`. Acceptance commits: `c9800b3` (skeleton) → `efaef43` (smoke OK).

**Goal**: minimum FastAPI app with the DB schema, middlewares and a starter setup wizard.

**What landed**:
- Project skeleton: `pyproject.toml`, `dreaming/main.py`, `dreaming/__init__.py`.
- Minimum FastAPI app on 8086 with `/health` (`96795d4`).
- SQLite schema fork from ALC + `project_id` (`5ee789b`).
- ProjectsService — CRUD + scan_projects_root (`c1cfc2e`).
- ConfigResolver — override-with-fallback (`10ae4fe`).
- setup_gate + project_resolver middleware + `project_not_found.html` (`2200281`).
- i18n loader + Jinja `t()` + CLDR Russian plurals (`3860dee`).
- Key-parity verifier `scripts/check_i18n.py` (`5da55c8`).
- Setup wizard: global config + projects_root scan + bulk import (`a529c9c`).
- /projects list, toggle, delete, import (`c174a89`).
- /settings minimal UI (`e1f0843`).
- Stub services + minimal scheduler (`df1849f`).
- End-to-end smoke (`efaef43`).

**Acceptance**: app starts, wizard works, projects register, idempotent import.

**Deferred**:
- Real ProcessManager (Wave 1).
- Sessions API (Wave 1).
- Pipeline pages (Wave 2).

## Wave 1 — Self-study core

**Tag**: `wave-1`. Acceptance commits: `a6ed585` → `b7824f9`.

**Goal**: nightly self-study + per-project dashboard + sessions REST API.

**What landed**:
- Port `keep_awake.py` from ALC (`1743d9a`).
- Port ProcessManager + project_id awareness (`a6ed585`).
- SqliteDB session/rotation domain methods (`79ac75f`).
- /api/session/start|finish (`e0e87cf`).
- Project-scoped routes `/p/{slug}/{,live,rotation}` + agents discovery (`6ef210f`).
- /p/{slug}/settings minimal UI (`651afcb`).
- Per-project nightly_learning_{slug} cron + register/unregister hooks (`5f9855e`).
- End-to-end smoke (`b7824f9`).

**Acceptance**:
- Session API works in multi-project mode.
- Dashboard renders week_stats.
- Rotation page with tier/enabled inline edit.
- Live SSE streaming.
- Nightly cron fires and starts claude.

**Deferred**:
- Pipeline pages (Wave 2).
- Topics, Kanban, Notes (Wave 2.1).

## Wave 2 — Pipeline pages

**Tag**: `wave-2`. Acceptance commits: `3b9995b`, `87fc009`, `f3270d3`, `8bd34b8`, `5a6f5b4`.

**Goal**: read-only pages for every ALC pipeline.

**What landed**:
- Wave 2.1 (3b9995b): Topics, Kanban, Notes.
- Wave 2.2 (87fc009): tech-debt parser + /findings + /tech-debt minimal.
- Wave 2.3+2.4 (f3270d3): Product Ideas board + Wiki bootstrap status.
- Wave 2.5 weekly_*_{slug} cron kinds + start_command project-scoping (8bd34b8).
- Smoke E2E for all 7 pipeline pages (5a6f5b4).

**Acceptance**:
- Every pipeline page renders without 500 (even with an empty dir).
- weekly_tech_debt_scan_{slug} registers when `weekly_tech_debt_scan_enabled=true`.

**Deferred**:
- TD detail / close / delete (Wave 2.5).
- Jira integration (Wave 2.5).
- Wiki bootstrap button (Wave 2.5).

## Wave 2.5 — Tech-debt + Jira + Wiki bootstrap

**Tag**: `wave-2.5`. Acceptance commit: `e39a0fe`.

**Goal**: actionable actions from the UI on pipeline pages.

**What landed**:
- TD detail page (`/p/{slug}/findings/{id}`).
- TD close (rewrite frontmatter `status: closed`).
- TD delete (unlink the file).
- Jira service (`dreaming/services/jira.py`).
- Ideas → Jira button with `jira_ticket: <key>` persisted into frontmatter.
- Wiki bootstrap button — `/p/{slug}/wiki/bootstrap` POST → `pm.start_command("/wiki-bootstrap")`.

**Acceptance**:
- The buttons actually do something.
- Per-project `jira_project_key` override works.
- Wiki bootstrap appears in `/p/{slug}/live` after a few seconds.

## Wave 3 lean — OrchestrationHub

**Tag**: `wave-3-lean`. Acceptance commit: `dcec547`.

**Goal**: DB-backed runs/nodes/messages for Roman flows + a minimal API endpoint set + UI for inspection.

**What landed**:
- Real `OrchestrationHub` impl: create_run, create_node, append_message, finish_run, ensure_stage, append_event, etc.
- 4 base API endpoints: `/api/orchestration/start`, `/{run_id}`, `.../message`, `/finish`.
- /p/{slug}/orchestration list page.
- /p/{slug}/orchestration/{run_id} detail page.
- One-Roman-per-project lock in `has_running_run` + 409.

**Acceptance**:
- A run can be created via curl and seen in the UI.
- The lock prevents creating a second parallel run.

**Deferred**:
- Spawning claude from POST /start (Wave 3.7).
- ClaudeSessionTail (Wave 3.6).
- SubagentWatcher (Wave 3.6).
- Cascade stages API (Wave 3.8).
- TTS, sidecar, contracts (Wave 3.9).

## Wave 3.6 — claude_session_tail / subagent_watcher / backfill

**Tag**: (no separate one, included in the `wave-3-full` peak). Commit: `75e67b0`.

**Goal**: real implementation of tail-watchers for Claude jsonl files.

**What landed**:
- `dreaming/services/claude_session_tail.py` — `tail_session_file`, `ClaudeSessionTail`, helpers (encode_workdir, find_session_file_by_id, find_recent_session_files, etc.).
- `dreaming/services/subagent_watcher.py` — `watch_subagents_for_run`, `SubagentWatcher`, `_resolve_node_for_subagent`.
- `dreaming/services/subagent_backfill.py` — `backfill_run` for offline replay.

**Acceptance**:
- Start a run, the file `~/.claude/projects/<workdir>/<session>.jsonl` updates live, messages appear in the DB.

**Deferred**: spawning claude from form-based start (Wave 3.7).

## Wave 3.7 — orchestration spawns claude

**Commit**: `f13babe`.

**Goal**: the form-based "Start Orchestration" button now actually starts claude and attaches watchers.

**What landed**:
- The form `POST /p/{slug}/orchestration/start` accepts `goal` and:
  - Creates run + root_node.
  - Spawns claude via `pm.start_command(session_id=claude_session_id)`.
  - Starts `ClaudeSessionTail` + `SubagentWatcher` via `asyncio.create_task`.
  - Saves the tasks to `app.state.orchestration_tails` and `orchestration_watchers`.
- `GET /refresh` — JSON for browser polling.
- `POST /resume` — `claude --resume <session_id>` + `interactive_stdin=True`.

**Acceptance**:
- Click Start, within seconds messages show up on the detail page.
- Resume works against an old session_id.

## Wave 3.8 — cascade pipelines API

**Commit**: `f59a8ea`.

**Goal**: API for cascade pipelines (5 stages with gates and artifacts).

**What landed**:
- 7 endpoints under `/api/cascade/`:
  - `init` (creates the run + 5 default stages).
  - `stage/start`, `stage/finish`.
  - `gate` (verdict).
  - `artifact` (with dedup_hash).
  - `message`.
  - `finish`.
- `dreaming/services/harness_client.py` — `HarnessClient` + `HarnessClientCache`.
- `dreaming/services/cascade_stage_detect.py` — heuristic detector.

**Acceptance**:
- `curl /api/cascade/init` creates a run and 5 stages.
- `dedup_hash` collision returns `{"id": null, "deduped": true}`.

**Deferred**: starter-kit slash commands `/cascade-task` and `/cascade-contract` — these are part of the external project, not DC.

## Wave 3.9 (Wave 3 full) — contracts + sidecar + tts stub

**Tag**: `wave-3-full`. Commit: `b49aafd`.

**Goal**: Wave 3 finalisation — add contracts page, sidecar findings page, tts_backfill stub.

**What landed**:
- `dreaming/services/contracts.py` + route + template.
- `dreaming/services/sidecar_findings.py` + route + template.
- `dreaming/services/tts_backfill.py` (stub).

**Acceptance**:
- /p/{slug}/contracts and /p/{slug}/sidecar-findings render.

**Deferred**:
- Real TTS backfill (stub returns 0).
- Full AskUserQuestion plumbing (table created in migration but the full API isn't there yet).

## Wave 4 lite — AI Usage analytics

**Tag**: `wave-4-lite`. Commit: `1c84f44a`/`1c84f44`/`1c84f44` — effectively `1c8...` (see `git log --grep "Wave 4 lite"`). The tag points to `1c8`.

**Goal**: per-project + global token usage.

**What landed**:
- `dreaming/services/ai_usage_parser.py` — incremental JSONL → `ai_usage_events`.
- `dreaming/services/ai_usage_stats.py` — `project_summary`, `global_summary`.
- `/p/{slug}/ai-usage` route + template.
- `/ai-usage` global route + template.
- Ingest cron (every 5 min).

**Acceptance**:
- Rows appear in the `ai_usage_events` table after the first ingest.
- Dashboard shows last_7d / last_30d totals + by_model.

## Wave 4 full — evolutions / loops / plans / cascade-costs

**Tag**: `wave-4-full`. Commit: `9841f53`.

**Goal**: 4 more read-only dashboards.

**What landed**:
- `dreaming/services/evolutions.py` + route + template.
- `dreaming/services/loops.py` + route + template.
- `dreaming/services/plans.py` + route + template (with progress%).
- `dreaming/services/cascade_costs.py` + route + template.
- Full ~80-key settings UI grouped by category (`4a44f02`).

**Acceptance**:
- All 4 pages render.
- Per-project + global settings UI shows every one of the 80+ keys.

## Wave 5 — aggregated dashboard

**Tag**: `wave-5`. Commit: `d33bd3c`.

**Goal**: the home page `/` shows per-project cards + global totals + active runs.

**What landed**:
- `index_dashboard.html` template.
- `root.py:index` collects stats for every project in one handler.
- Cross-project metrics: total success/failed/timeout/running, sum td/ideas, wiki_present.
- Active runs aside.
- README/CLAUDE.md final.

**Acceptance**:
- `/` renders N cards (one per enabled project).
- Active running keys are displayed.

## Not implemented yet

As of `wave-3-full` (last commit `b49aafd`) the deferred list is:

- **Real TTS backfill** (`tts_backfill.backfill_tts` — stub returns 0).
- **Full AskUserQuestion plumbing** — the `orchestrator_questions` table already exists, but API endpoints for create / answer aren't added yet. ProcessManager watchdog already accounts for a pending question ([`process_manager.py:561`](../../dreaming/services/process_manager.py)).
- **codex / continue runners** — the `orchestration_local_runner` config exists but the code only paths claude.
- **work_routing_mode** — the setting exists, unused in code.
- **Real harness integration via UI** — the `HarnessClient` service is ready, but `/p/{slug}/orchestration/start` doesn't call it (uses local claude). Wiring possible via changing `start_command` and checking `await harness_clients.get_for_project(...)`.
- **Smoke tests for Wave 3+** — separate smoke scenarios exist, but no end-to-end orchestration smoke is written.

## Cross-references

- Where each piece of code lives — [`services.md`](services.md), [`routes.md`](routes.md).
- Which settings are active per wave — [`configuration.md`](configuration.md).
- Architecture — [`architecture.md`](architecture.md).
