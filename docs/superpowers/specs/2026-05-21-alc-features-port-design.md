---
date: 2026-05-21
status: draft
topic: alc-features-port
---

# Porting 6 ALC features into ai-dreaming-center

## Problem

The agent-learning-center (ALC) at `D:\Work\RsCloud2022\agent-learning-center` is a mature single-project FastAPI dashboard. The ai-dreaming-center (ADC) is its multi-project fork. Six ALC features are either substantially better in ALC or missing entirely in ADC:

| Feature | ALC | ADC |
|---|---|---|
| Orchestration | SSE log stream + 5-stage swimlane viz + activity chips, parsed `[agent_spawn]`/`[agent_update]`/`[agent_done]` markers | Polling-based list + plain message table, no visualization |
| Home (Главная) | Bento grid of 13 AJAX-reloadable tiles via `dashboard_tiles.py` | Plain stats numbers + project cards |
| Tech-debt | List view with sort/filter + single-item view rendering TD-\*.md frontmatter | Stats-only stub (counts by status/module) |
| Evolutions | List + rubric pass/fail/warning aggregation grid + per-agent reports browser | List + status management; no rubric |
| Loops templates | CRUD (new/edit/delete) + **16 seeded templates** auto-installed if dir is empty | Catalog stub: reads `.md` files, no CRUD, no seeds |
| Review | Filters pipelines in `reviewing/local_build/mr` phases | Concept doesn't exist — ADC has no `pipelines` table |

The user has called out Orchestration as the highest priority ("у нас намного хуже"). They also explicitly want the 16 loop template seeds carried over.

## Goals

- Port ALC's orchestration UI (SSE streaming, swimlane stage rail, activity chips, log grouping by stage) into ADC's per-project orchestration detail page, reusing the existing `orchestrator_*` schema.
- Port the 16 loop templates from ALC's `_SEEDS` list, seeded into each ADC project's `<working_dir>/.claude/loops/templates/` on project enable (autoconfig hook), plus a CRUD UI on `/p/{slug}/loops/templates`.
- Port ALC's tech-debt list view + single-item view into `/p/{slug}/findings` (ADC already has parser + routes; the gap is UI).
- Port the evolution rubric aggregation panel into ADC's evolutions page.
- Port ALC's bento-tile dashboard architecture into ADC, scoped per-project (and a cross-project aggregate view on global `/`).
- Add a Review (triage) page at `/p/{slug}/review` that aggregates items needing attention (proposed evolutions, open tech-debt, sidecar findings).

## Non-goals

- Cross-project orchestration (out of scope per ADC's existing design).
- Schema changes to `orchestrator_*` tables — they already include `stages`, `events`, `nodes`, `messages`. Wave A derives stage association for events by JOIN through `orchestrator_nodes.stage_id` rather than denormalizing.
- Removing the existing `/p/{slug}/orchestration/{run_id}/refresh` polling route — kept as JS-disabled fallback.
- Migrating ALC data into ADC — greenfield seeding only.
- Adding tests/CI — ADC inherits ALC's "no test suite" choice (smoke scripts only).
- Globalizing the loop templates directory. Seeds live inside the project's working directory, not a shared/global folder.
- Replacing the existing polling endpoint `/p/{slug}/orchestration/{run_id}/refresh`. It stays as a fallback; SSE is the new primary path.
- Per-stage cost roll-ups in orchestration — those live in `/p/{slug}/cascade-costs` already and stay there.

## Architecture

The work is organized into six waves. Each wave is independently shippable, ends with a smoke check, and is tagged `wave-A` … `wave-F`. Order is chosen so high-UX-impact, low-blast-radius changes ship first, leaving the broadest UI refactor (E) for after the underlying data sources are richer.

```
Wave A  Orchestration SSE + swimlane            ── highest UX delta, isolated
Wave B  Loop templates: 16 seeds + CRUD UI      ── unblocks stub
Wave C  Tech-debt list + single-item view       ── UI on existing parser
Wave D  Evolution rubric panel                  ── small additive
Wave E  Bento-tile dashboard                    ── per-project + global
Wave F  Review triage page                      ── depends on C being a per-project list
```

---

### Wave A — Orchestration SSE + swimlane

**Goal:** Replace the current polling-driven detail page with live SSE updates and a 5-stage cascade swimlane (queued / active / done / rejected activity chips per stage), matching ALC's `orchestration.html` layout.

**Source files in ALC to mirror:**
- `app/services/claude_session_tail.py` (931 LOC — parser for `[agent_spawn]/[agent_update]/[agent_done]` and stage markers). ADC already has `dreaming/services/claude_session_tail.py` (502 LOC); the gap is the stage-grouping logic and SSE event emission.
- `app/routes/orchestration.py` — the `GET /orchestration/{run_id}/stream` endpoint using `sse_starlette.EventSourceResponse`.
- `app/templates/orchestration.html` (926 LOC) — the two-panel layout: left runs list, right cascade rail + swimlane body.

**Target files in ADC:**
- `dreaming/routes/project_orchestration.py` — add `GET /p/{slug}/orchestration/{run_id}/stream` returning `EventSourceResponse`. Event payload shape: `{"id": event_id, "event": "stage_update" | "message" | "node" | "done", "data": {...}}`.
- `dreaming/services/orchestration_hub.py` — add `async def stream_run_events(project_id, run_id)` async generator. Yields:
  - Initial snapshot: full `stages`, `nodes`, `messages` (so clients connecting mid-run get state)
  - Incremental: new rows from `orchestrator_events` since last seen `id` (poll every 500ms; this is in-process, the table is small per run)
  - Stage association of each event is derived via JOIN: `orchestrator_events` → `payload_json.node_id` → `orchestrator_nodes.stage_id`. The events table itself has no `stage_id` column (verified schema: `id, run_id, ts, event_type, payload_json`). Events with no `node_id` in payload are tagged as stage-agnostic.
  - Terminates when run status ∈ `{success, fail, timeout, canceled}` AND no new events for 3s
- `dreaming/services/claude_session_tail.py` — already produces `orchestrator_events` rows. The gap (if any) is the stage-tagging regex from ALC's parser (ALC's `claude_session_tail.py` lines 29-45). During implementation: read ADC's parser end-to-end first and only add what's missing — do not regress existing parsing.
- `dreaming/templates/project_orchestration_detail.html` — replace polling JS with `EventSource`. Layout:
  - Top bar: run id, status badge, goal preview, "force-finish" button, link back to list.
  - Stage rail: one cell per row in `orchestrator_stages` for this run, ordered by `stage_index`. Each cell shows: `label` (from `orchestrator_stages.label`), `status`, `iteration`, elapsed time, message count. The number of cells is dynamic — typically 5 for cascade runs but the rail does not hard-code that. Stage identity is `stage_key` (verified column name; there is no `kind` column).
  - Swimlane body below the rail: for each stage row, a horizontal track of activity chips. Each chip is a `node` (rows in `orchestrator_nodes` for this stage) with current state derived from `orchestrator_events` events about that node — clicking a chip opens its messages in a slide-over panel.
  - History fade: older chips dimmed via opacity (matches ALC's `dim-history` CSS).
- `dreaming/static/orchestration_stream.js` — new file, EventSource client. On each event, mutate the relevant DOM node (chip color, message append, stage progress). On EventSource `error` (network drop, server restart) falls back to polling `/refresh` until SSE reconnects. After normal stream completion (server-side `done` event + close) the client does NOT start polling.

**Data flow:**
```
Claude CLI stdout
        │
        ▼
ProcessManager._consume_*_stream  ──► claude_session_tail.parse_line
        │                                   │
        │                                   ▼
        │                         orchestrator_events INSERT
        │                         (with stage_id when known)
        ▼
EventSource client ◄── EventSourceResponse ◄── orchestration_hub.stream_run_events
   on /p/{slug}/orch/{id}/stream     │
                                      └── tails orchestrator_events.id > cursor
```

**Acceptance:**
- Start an orchestration run. Detail page shows stage rail, swimlane fills as agents spawn, chips change color as they progress.
- Kill the browser tab mid-run, reopen — page shows current state correctly (initial snapshot works).
- Run completes → SSE closes via server-sent `done` event; polling does NOT restart.
- Mid-run SSE error → client falls back to `/refresh` polling and continues updating; resumes SSE on next page load.
- Disable JavaScript → page renders initial state via server-side render and shows a "live updates disabled" hint.
- Smoke: `scripts/smoke_orchestration.py` (new) hits the stream endpoint, asserts at least one event arrives within 5s of a synthetic run.

**Risks:**
- ADC's `claude_session_tail.py` may emit different markers than ALC. Mitigation: read ADC's parser end-to-end during implementation and add only the missing regexes; do not regress existing parsing.
- SSE behind reverse proxy: not applicable for ADC's local-only deployment, but document in `CLAUDE.md` for future readers.

---

### Carried over from Wave A (deferred follow-ups)

The Wave A implementation acknowledged two race windows in code TODOs; both are tolerable for a single-user local dashboard but should be closed before any multi-client deployment. Track them in the first Wave B/C plan that touches the relevant files:

- **Stage-id null-window race** (`orchestration_dispatch.start_orchestration_run`): the root node is INSERTed with `stage_id=NULL` before the subsequent UPDATE sets the stage_id. Fix by extending `hub.create_node` to accept an optional `stage_id` and inlining it, OR by moving the stage seed to BEFORE `create_node` and passing the new id.
- **Snapshot-vs-cursor priming race** (`OrchestrationHub.stream_run_events`): events appended between snapshot reads (`list_stages`/`list_nodes`/`list_messages`) and the cursor priming `list_events_since(after_ts=None)` are silently dropped. Fix by priming the cursor FIRST, then reading the snapshot; tolerate one possible duplicate event on first tail iteration (clients already mutate-by-id, duplicates are harmless).

Plus minor follow-ups: per-agent chip click → message slide-over panel, `appendMessage` placeholder backfill via fetch, stage-marker parsing in `claude_session_tail.py` to auto-tag events.

### Wave B — Loop templates: 16 seeds + CRUD UI

**Goal:** Replace the stub `/p/{slug}/loops/templates` (read-only catalog) with a full CRUD UI, and seed 16 loop templates into each project's `<working_dir>/.claude/loops/templates/` automatically on project enable.

**Source files in ALC to mirror:**
- `app/services/loop_templates.py` — `LoopTemplate` dataclass + `list_templates`/`read_template`/`write_template`.
- `app/services/loop_templates_seed.py` — `_SEEDS` list (16 entries) and `seed_if_empty()` (function around line 357).
- `app/templates/loop_templates_list.html` + `app/templates/loop_template_view.html`.
- `app/routes/loop_templates.py` — full CRUD route set.

**Target files in ADC:**
- `dreaming/services/loop_templates.py` (new) — port `LoopTemplate` dataclass and the `list_templates/read_template/write_template` functions. Adapt path: takes `working_dir` instead of a global config path; resolves to `<working_dir>/.claude/loops/templates/`.
- `dreaming/services/loop_templates_seed.py` (new) — copy `_SEEDS` verbatim from ALC. Adapt `seed_if_empty(working_dir)` signature.
- `dreaming/routes/project_loops_templates.py` — replace current `_scan_templates` inline fn with calls to the new service. Add routes:
  - `GET /p/{slug}/loops/templates` — list (already exists, swap to new service)
  - `GET /p/{slug}/loops/templates/new` — create form
  - `GET /p/{slug}/loops/templates/{tpl_slug}` — edit form
  - `POST /p/{slug}/loops/templates` — save (create or update; slug in form picks branch)
  - `POST /p/{slug}/loops/templates/{tpl_slug}/delete` — delete
- `dreaming/templates/project_loops_templates.html` — replace stub with ported list view.
- `dreaming/templates/project_loops_template_view.html` (new) — edit/create form (textarea for body, inputs for frontmatter fields).
- **Seeding hook:** call `seed_if_empty(project.working_dir)` from the autoconfig pipeline. Search `dreaming/services/autoconfig.py` for the existing project-enable hook and add the seed call there. Do NOT call seeding from the GET route — seeding is bootstrap-only.
- **i18n:** add `loops.templates.*` keys to `messages_ru.json` and `messages_en.json` (button labels, column headers, confirm dialogs). Seed body text stays Russian (carried over from ALC).

**Acceptance:**
- Enable a fresh project → its `.claude/loops/templates/` ends up with 16 `.md` files.
- Re-enable / re-import → no duplicates created (idempotent via `seed_if_empty`'s skip-existing check).
- Create a new template via UI → file appears on disk with correct frontmatter.
- Edit then save → file updated, mtime changes.
- Delete via UI button (confirm dialog) → file removed.
- Smoke: `scripts/smoke_loop_templates.py` (new) imports the new service, asserts seed count == 16 for a tmp working_dir.

**Idempotency note (correcting earlier draft):** `seed_if_empty` in ALC does NOT actually require an empty directory. It iterates the seed list and skips entries whose target slug already exists on disk, writing only missing ones. So re-running it after a user has added their own templates is safe: their files are untouched, and any missing seed is filled in. The name is historical; the behavior is "fill in any missing seeds". ADC keeps this behavior.

**Risks:**
- Frontmatter parser already exists in ALC; ADC needs `pyyaml` to handle the same shape (`yaml.safe_load` already in deps).

---

### Wave C — Tech-debt list + single-item view

**Goal:** Replace the stats-only `/p/{slug}/tech-debt` page (just counts) with the full list view ALC has, and add a single-item view route. ADC's parser (`dreaming/services/tech_debt.py`) is already fine — gap is UI.

**Source files in ALC:**
- `app/templates/findings.html` (21,651 bytes — sort, filter, badge logic)
- `app/templates/td_view.html` — single-item view with rendered markdown body + frontmatter badges
- `app/routes/findings.py` — `GET /findings`, `GET /findings/{td_id}/view`, `POST /findings/{td_id}/close|delete`

**The actual gap is the templates.** ADC's `dreaming/routes/project_findings.py` already implements the full route set: list, single-item, close, delete, status, github, orchestrate. The page is "stats-only" because `project_findings.html` and `project_findings_detail.html` render minimal layouts.

**Target files in ADC:**
- `dreaming/templates/project_findings.html` — replace with ALC's `findings.html` layout: filter chips at top (status / module), columns `[id, title, status, priority, module, complexity, autonomy, confidence, created]`, sortable column headers. Filtering and sorting are server-side via query params; route already accepts them or needs trivial extension.
- `dreaming/templates/project_findings_detail.html` — replace with ALC's `td_view.html`: frontmatter badges row + markdown-rendered body + action buttons (close, delete with confirm dialog).
- `dreaming/routes/project_findings.py` — extend the GET list handler to accept `?status=`, `?module=`, `?sort=` query params if not already supported. Verify during implementation.
- The current `/p/{slug}/tech-debt` page (stats-only) STAYS as a dashboard summary; the list view lives at `/p/{slug}/findings`. Add a sidebar link "Tech debt items" → `/p/{slug}/findings`.

**Acceptance:**
- Page renders all TD-\*.md files for the project.
- Filter chips work without page reload (server-side rendered on each chip click is fine — no JS state machine needed).
- Sort by clicking column headers.
- Single-item view renders frontmatter as badges and markdown body cleanly.
- Close button updates `status:` in frontmatter via in-place edit on the file.
- Smoke: `scripts/smoke_findings.py` (new) creates a TD-\*.md fixture, hits all routes, asserts state transitions.

---

### Wave D — Evolution rubric panel

**Goal:** Add a rubric aggregation panel to `/p/{slug}/evolutions`, showing how many of the project's evolution proposals have rubric metadata and how the verdicts break down.

**Source files in ALC:**
- `app/services/evolution_rubric.py` (241 LOC) — `collect_stats(evolutions_dir)` returns `ReportRubricStats(total, with_rubric, auto, review, reject, incomplete)`. Verdict buckets are `auto / review / reject / incomplete` (decided by the rubric rules: `auto` = evidence≠weak AND durability≠one_off AND safety≠unsafe; `reject` = unsafe; `review` = otherwise; `incomplete` = rubric block partial). Aggregation is **across the whole evolutions dir, not per agent**. Scans `*.md` glob, skips entries with `_` prefix.

**Target files in ADC:**
- `dreaming/services/evolution_rubric.py` (new) — port `collect_stats(evolutions_dir)` verbatim including the `ReportRubricStats` dataclass and the rubric parsing helpers (`parse_rubric`, `parse_rubric_from_file`, `extract_frontmatter`).
- `dreaming/routes/project_evolutions.py` — already resolves the project's evolutions directory (currently `.claude/agents/_context/`). Pass that directory into `collect_stats`. Add `rubric_stats` to template context.
- `dreaming/templates/project_evolutions.html` — add a rubric panel above the existing list: a single horizontal stat strip showing `total`, `with_rubric`, and the four verdict-bucket counts (`auto`, `review`, `reject`, `incomplete`) as labeled badges. Optional bar/donut visualization is a stretch — start with badges.

**Scope clarification — not in this wave:** per-agent grouping. ALC's rubric is project-wide; we keep that. If per-agent breakdown is wanted later, it's a follow-up.

**Acceptance:**
- Page renders rubric stats from existing evolution files. If `with_rubric == 0`, panel shows "no rubric data yet" hint.
- Stats compute fresh each request (no caching).
- Smoke: optional — manual visual check with at least one fixture file containing a rubric frontmatter block.

**Risks:**
- ADC evolution files may not contain rubric blocks (older `/evolve-agent` versions don't emit them). Expected outcome: `total > 0`, `with_rubric == 0`, panel renders the empty-data hint. That's correct behavior, not a bug.

---

### Wave E — Bento-tile dashboard

**Goal:** Replace the current plain home pages (global `/` and per-project `/p/{slug}/`) with ALC's bento-tile architecture: AJAX-reloadable tiles, error-resilient layout, polling-based "running" indicator in navbar.

**Source files in ALC:**
- `app/services/dashboard_tiles.py` (309 LOC) — 13 `build_*_tile()` async builders.
- `app/templates/dashboard.html` (3,773 bytes) — bento grid layout
- `app/templates/partials/dashboard/_tile_*.html` — 13 tile partials
- `app/routes/dashboard.py` — `GET /` + `GET /api/dashboard/tile/{tile_id}` (AJAX endpoint)

**Target files in ADC:**
- `dreaming/services/dashboard_tiles.py` (new) — port tile builders. Each builder gets `(db, project_id)` and returns tile data. Some tiles are reused for both per-project and global views with the global view aggregating across all projects.
- `dreaming/routes/project_dashboard.py` — replace existing render with new tile-driven layout. Add `GET /p/{slug}/api/dashboard/tile/{tile_id}` for AJAX reload.
- `dreaming/routes/root.py` — global `/` becomes a cross-project aggregate, same partial structure with different builders.
- `dreaming/templates/project_dashboard.html` + `dreaming/templates/index_dashboard.html` — replaced with bento grid (both files are already in `git status` modified list — fine to overwrite contents).
- `dreaming/templates/partials/dashboard/_tile_*.html` (new dir) — per-tile partials.
- **Tile inventory** (subset adapted to ADC's data sources):
  - `alerts` — failed sessions, stale runs
  - `pipeline` — orchestration progress summary (count by stage)
  - `ai_cost` — `ai_usage_events` weekly cost
  - `loops` — running loops + last completion
  - `orchestration` — active runs
  - `evolutions` — proposed/applied counts
  - `sidecar` — recent findings count
  - `cascade_cost` — `cascade_costs` rollup
  - `learning_week` — sessions this week
  - `activity_feed` — union of recent events
  - `weekly_jobs` — scheduled jobs for this project from scheduler
  - `anomalies` — error rate spikes (if data source exists; skip otherwise)
  - `under_studied` — agents with no recent activity (port if ADC has equivalent)

**Acceptance:**
- Per-project home shows tiles populated from that project's data only.
- Global home shows the same tile types with cross-project aggregations.
- Failed tile (e.g., a missing-dir error) renders an error placeholder, other tiles still load.
- AJAX endpoint returns a single tile's rendered HTML for in-place reload.
- Smoke: existing dashboard smoke + manual visual check.

**Risks:**
- This is the biggest wave by scope. Spread implementation across multiple PRs; each tile is independent. Suggest sub-steps: (E1) layout shell + 3 simplest tiles, (E2) cost tiles, (E3) orchestration/loops tiles, (E4) activity feed + remaining.

---

### Wave F — Review (triage) page

**Goal:** Add `/p/{slug}/review` as a triage view aggregating items that need user attention. Reinterpreted from ALC's pipeline-based review (which doesn't fit ADC's domain) into a per-project triage of: proposed evolutions, open tech-debt items flagged for review, and sidecar findings.

**Target files in ADC:**
- `dreaming/routes/project_review.py` (new) — `GET /p/{slug}/review`. Queries:
  - Evolutions with frontmatter `status: proposed` (via `dreaming.services.evolutions.list_evolutions(evolutions_dir)` — note: ADC uses `list_evolutions`, not ALC's `list_overrides`)
  - Tech-debt items with `status: open` AND priority in `{high, urgent}` (via `dreaming.services.tech_debt.parse_tech_debt`)
  - Sidecar findings recent / unread (from existing sidecar service)
- `dreaming/templates/project_review.html` (new) — grid with 3 sections (Evolutions / Tech-debt / Sidecar), each showing top N items with a link to the canonical detail page.
- Sidebar entry under project section, pointing to `/p/{slug}/review`.

**Acceptance:**
- Page renders empty placeholders when no items qualify.
- Each card links to the canonical page (`/p/{slug}/evolutions`, `/p/{slug}/findings/{id}`, etc.).
- No new data sources — pure aggregation of existing services.
- Smoke: optional; visual check after fixtures exist.

**Risks:**
- The criteria for what shows up in "review" is a product judgment call. Default to broad inclusion; revisit with the user after the first iteration ships.

---

## Cross-cutting concerns

### i18n
Every new template uses `{{ "key" | t(locale=locale) }}`. RU is default. EN keys mirror RU keys. Verified by `scripts/check_i18n.py` per existing conventions (`CLAUDE.md`).

### File encoding
New JSON / Cyrillic-containing templates written via Write/Edit tool (UTF-8), never via PowerShell `Set-Content` (which defaults to UTF-16 LE).

### Smoke tests
Each wave ships a `scripts/smoke_<wave>.py` script following the pattern in `scripts/smoke_topics.py`. No automated CI — these are manual `python scripts/smoke_*.py` runs.

### Git tagging
Wave done → `git tag wave-A` … `wave-F`. Smoke must pass before tagging.

### Sidebar / navigation
After each wave, verify the per-project sidebar (`dreaming/templates/_sidebar.html`) lists the new/changed pages. EN + RU labels added together.

## Open questions for review

1. Wave order — recommended A→F as above. Alt: prioritize B if seeding-on-import is more urgent than orchestration visualization.
2. Wave E scope — porting all 13 tiles is large. Could split into E-core (4 tiles) + E-extended (rest) and ship E-core first.
3. Review page (Wave F) criteria — proposed defaults above are conservative; user may want different inclusion rules.
