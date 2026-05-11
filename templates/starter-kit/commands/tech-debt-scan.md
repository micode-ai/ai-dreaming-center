---
description: Scan the repository for tech-debt items and write Markdown findings.
---

You are running inside Claude Code, spawned by the AI Dreaming Center
(weekly scanner or on-demand) to scan this project for technical debt and
write per-item Markdown files into `docs/tech-debt/`.

## What you have

- `cwd` is the project repository root.
- Target directory: `docs/tech-debt/` (already created by DC).
- Env vars: `LEARNING_SESSION_ID`, `DREAMING_API_URL`, `DREAMING_PROJECT_SLUG`.

## What to do

1. **Sample the repo for debt smells.** Cheap signals:
   - `TODO`, `FIXME`, `HACK`, `XXX` comments — grep for these.
   - Files mentioned as "legacy", "deprecated", or "needs refactor" in
     README / CLAUDE.md / commit messages.
   - Files modified by many recent commits (churn = often debt).
   - Tests skipped (`.skip`, `xdescribe`, `xit`, `@pytest.skip`).
   - Files >1000 lines (often a smell on their own).
   - Duplicated logic across files (sample a couple of utilities).

2. **Pick the top 5–10 most actionable items.** Each item must be:
   - **Concrete** — names specific file(s) and lines.
   - **Bounded** — could be tackled in <1 day.
   - **Worth doing** — has a real cost (slowing development, hiding bugs,
     blocking a feature).

3. **For each item, write `docs/tech-debt/{slug}.md`** where `{slug}` is a
   short kebab-case id like `auth-middleware-duplication` or
   `legacy-payment-validator`:

   ```markdown
   ---
   id: {slug}
   title: '{short one-line title — wrap in single quotes}'
   status: open
   priority: P2     # P1 hot / P2 normal / P3 nice-to-have
   module: '{top-level module or package, e.g. apps/api}'
   created_at: {YYYY-MM-DD}
   ---

   # {title}

   ## What's wrong
   One paragraph describing the smell. Be specific — quote file paths.

   ## Why it matters
   One paragraph: what's the actual cost today, and what gets worse if
   ignored.

   ## Proposed fix
   3–5 bullets describing the change.

   ## Files involved
   - `path/to/file1.ext`
   - `path/to/file2.ext`
   ```

   Front-matter is parsed by the DC tech-debt page. Keep `id` matching the
   filename (without `.md`).

   **YAML escaping (critical — broken frontmatter is silently dropped by
   the parser):** always wrap `title` and `module` in single quotes. A bare
   value can't safely contain `"`, `:`, `?`, or `—`. Inside single-quoted
   YAML strings, a single quote is doubled (`'don''t'`). Don't mix quotes
   (e.g. `title: "foo" — bar` is invalid YAML).

4. **Don't duplicate** — read existing files in `docs/tech-debt/` first; if
   an item is already filed, skip it.

5. **Report back:**

   ```bash
   curl -s -X POST "$DREAMING_API_URL/api/session/finish" \
     -H "Content-Type: application/json" \
     -d "{\"session_id\":\"$LEARNING_SESSION_ID\",\"status\":\"success\"}"
   ```

   On failure, send `"status":"failed"` with `"error_message"`.

## Rules

- Do **not** edit code, only write files in `docs/tech-debt/`.
- Do **not** invent debt where none exists — if you can't find 5 real
  items, write fewer.
- Use absolute repo-relative paths in file references (no `/tmp/`, no
  absolute disk paths).
