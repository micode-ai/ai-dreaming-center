# Smoke Tests

Manual verification scripts. Run after each wave's acceptance criteria are claimed met.

## Wave 0 — Foundation
1. Server boots: `python -m uvicorn dreaming.main:app --port 8086` returns no traceback; `curl localhost:8086/health` -> `{"ok": true}`.
2. Empty-DB redirect: visit `http://localhost:8086/` -> 303 to `/setup`.
3. Setup wizard: at `/setup`, scanner shows 11 directories under `d:\Work\micode\`. Submitting all checked -> DB has 11 rows in `projects`.
4. `/projects` lists 11 entries.
5. `/p/UNKNOWN/` -> 404 with "project not found".
6. i18n: switching `dc_locale` cookie to `en` changes navbar labels (verify after messages_en.json populated).

(Waves 1-5 add their own sections.)
