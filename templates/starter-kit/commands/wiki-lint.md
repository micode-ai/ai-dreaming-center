---
description: Check docs/wiki/ for staleness — pages referencing files that no longer exist.
---

You are running inside Claude Code, spawned by the AI Dreaming Center
(weekly lint job) to keep `docs/wiki/` in sync with the actual repository.

## What you have

- `cwd` is the project repository root.
- Wiki dir: `docs/wiki/` (already exists with domain pages from `/wiki-bootstrap`).
- Env vars: `LEARNING_SESSION_ID`, `DREAMING_API_URL`, `DREAMING_PROJECT_SLUG`.

## What to do

1. **List every file in `docs/wiki/`** (Glob `docs/wiki/**/*.md`).

2. **For each wiki page:**
   - Read it.
   - Find every file reference it makes (anything that looks like a path:
     `path/to/file.ext`, ``` `pkg/foo.py` ```, links in markdown).
   - Check each referenced path actually exists in the repo.

3. **Identify stale pages.** A page is stale if:
   - It references a file that no longer exists (renamed, deleted).
   - Its "Entry points" section has paths that don't resolve.
   - Domain it describes is no longer present (e.g. `payments.md` but no
     `apps/payments/` directory).

4. **Fix what's fixable, flag what's not:**
   - If a renamed file is easy to identify (e.g. moved to a new directory),
     update the reference in the wiki page.
   - If the change is substantial (domain reorganised, file genuinely
     gone), add a note at the top of the page:
     ```markdown
     > **⚠ stale ({YYYY-MM-DD}):** N references no longer resolve. See "Lint findings" below.
     ```
     And append a "Lint findings" section listing the broken references.

5. **If a whole domain is gone**, don't delete the page — rename to
   `_archived-{name}.md` (parser ignores files starting with `_`) and keep
   it for history.

6. **Write a one-shot summary** at the end of the run to
   `docs/wiki/_lint-{YYYY-MM-DD}.md` listing what was checked, what was
   fixed, what's still stale.

7. **Report back:**

   ```bash
   curl -s -X POST "$DREAMING_API_URL/api/session/finish" \
     -H "Content-Type: application/json" \
     -d "{\"session_id\":\"$LEARNING_SESSION_ID\",\"status\":\"success\",\"note_path\":\"docs/wiki/_lint-{date}.md\"}"
   ```

## Rules

- Do **not** delete wiki files outright — rename to `_archived-*.md`.
- Do **not** edit files outside `docs/wiki/`.
- Don't re-do a `/wiki-bootstrap` — that's a separate command.
