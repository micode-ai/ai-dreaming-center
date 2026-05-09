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
