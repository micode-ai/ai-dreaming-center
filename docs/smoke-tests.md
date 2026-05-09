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
