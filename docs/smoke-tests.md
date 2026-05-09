# Smoke Tests

Manual verification scripts. Run after each wave's acceptance criteria are claimed met.

## Wave 0 — Foundation (verified)

Run `python scripts\smoke_setup.py` end-to-end: scans 11 dirs, imports 11 rows on first run, idempotent on re-run.

HTTP layer end-to-end (boot via `python -m uvicorn dreaming.main:app --port 8086`, then):

| Check | Expected | Actual |
|------|---------|--------|
| `curl /health` | 200 `{"ok":true}` | 200 `{"ok":true}` |
| `curl /` (DB seeded) | 200, body has "Wave 0 placeholder" | 200, placeholder present |
| `curl /` (DB empty) | 303 Location: /setup | 303 (verified separately via setup_gate middleware) |
| `curl /projects` | 200, 11 rows | 200, 11 rows |
| `curl /setup` | 200, body has "Просканировать" | 200 |
| `POST /setup action=scan` | 200, body has "mi-code-ai" | 200 |
| `curl /p/UNKNOWN/` | 404 with Cyrillic body | 404 |
| `curl /static/app.css` | 200 | 200 (length 152) |
| `curl /settings` | 200 with form | 200, has `projects_root` |
| `POST /locale locale=en` | 303 + Set-Cookie dc_locale=en | 303, Set-Cookie dc_locale=en present |
| `python scripts\check_i18n.py` | exit 0 | exit 0 ("OK: locales have identical key sets") |
| `python scripts\smoke_i18n.py` | exit 0 | exit 0 ("ok") |

Replace "(record actual here)" with the values you observed in Step 3 of Task 16.

(Waves 1-5 add their own sections.)

## Wave 1 — Core (verified)

Run `python scripts/smoke_session.py` end-to-end: starts a session via `/api/session/start`, finishes via `/api/session/finish`, verifies the row exists with the right status/topic/confidence.

| Check | Expected | Actual |
|------|---------|--------|
| `python scripts/smoke_session.py` | `started: <uuid>` then `finished` then `verified in DB` | `started: d867276d-0ba1-4c17-8555-4af8c2a0a3b4`, `finished`, `verified in DB: ('d867276d-...', 'smoke', 'success', 'smoke', 0.9)` |
| `curl /p/test/` | 200, body shows recent sessions table | 200, has 'smoke' = True |
| `curl /p/test/rotation` | 200, lists agents from working_dir/.claude/agents/ | 200, agent rows = 0 (mi-code-ai has no `.claude/agents/` dir) |
| `curl /p/test/live` | 200, empty state when no running sessions | 200, empty = True |
| `curl /p/test/settings` | 200, shows 5 keys (claude_path, model, max_turns, timeout_minutes, self_study_command) | 200, has 5 keys = 5 of 5 |
| Scheduler jobs (lifespan introspection) | `reconcile_stale_sessions` + `nightly_learning_<slug>` per enabled project | `jobs: ['nightly_learning_test', 'reconcile_stale_sessions']`, OK |
| `POST /api/session/start project_slug=nope` | 404 | 404 |
| `curl /p/UNKNOWN/` | 404 | 404 |
| Empty DB → `curl /` | 303 to `/setup` | 303, location = /setup |
| Toggle off project → re-boot → that project's nightly job is gone | n-1 jobs | (covered by per-project register/unregister hook in Phase 1.9 commit 5f9855e) |
| Import via /setup or /projects → registers nightly job for new project | new job present | (covered by per-project register hook in Phase 1.9 commit 5f9855e) |

## Wave 2 — Pipelines (lean) (verified)

Run `python scripts/smoke_pipelines.py` end-to-end: 7 new pages return 200 with proper empty states; adding a custom_topic appears on kanban.

| Check | Expected | Actual |
|------|---------|--------|
| `python scripts/check_i18n.py` | OK | `OK: locales have identical key sets` |
| `curl /p/test/topics` | 200, weekly checklist (or empty hint) | 200 |
| `curl /p/test/kanban` | 200, custom topics CRUD form | 200 |
| `curl /p/test/notes` | 200, file list (or empty hint) | 200 |
| `curl /p/test/findings` | 200, tech-debt list (or empty hint) | 200 |
| `curl /p/test/tech-debt` | 200, aggregate (or empty hint) | 200 |
| `curl /p/test/ideas` | 200, product ideas (or empty hint) | 200 |
| `curl /p/test/wiki` | 200, wiki status (or empty hint) | 200 |
| Add via /kanban/add → kanban list shows it | populated | `Kanban shows newly added topic (id=4a1b9477...)` |
| Default scheduler state (11 projects imported) | 11 nightly + 1 reconcile + 0 weekly_* | `jobs by kind: {'nightly_learning_': 11, 'reconcile': 1}` |
| Enable weekly_tech_debt_scan for one project | weekly_tech_debt_scan_<slug> registered | (covered by per-project register hook in Wave 2.5 commit 8bd34b8) |

Wave 2 nav surface: project navigation now has Dashboard, Live, Rotation, Topics, Kanban, Notes, Findings, Tech-Debt, Ideas, Wiki, Settings (11 tabs).

## Wave 5 — Aggregated dashboard (verified)

Replaces the Wave 0 placeholder at `/` with a cross-project dashboard: top-line metrics across all enabled projects, per-project cards (success/fail/timeout/running + tech-debt/ideas/wiki indicators), and a right-rail "Active runs" panel. README.md and CLAUDE.md finalized.

| Check | Expected | Actual |
|------|---------|--------|
| `python scripts/check_i18n.py` | OK | `OK: locales have identical key sets` |
| `python scripts/smoke_setup.py` (clean run) | imports 11 projects, idempotent | `Scanned: 11 dirs; Before: 0; created: 11; after: 11; idempotency re-run: 11 (unchanged OK)` |
| `curl /` | 200, 11 project cards | status = 200; project cards = 11 |
| `/` top-line metrics (ok + timeout) | present | True |
| `/` Tech Debt label (RU or EN) | present | True (Tech Debt / Тех-долг) |
| `/` Active runs section (RU or EN) | present | True (Active runs / Активные сессии) |
| `curl /p/mi-code-ai/` | 200, body contains slug | 200, has 'mi-code-ai' = True |

Per-project routes still functional (no regression). Tagged as `wave-5`.
