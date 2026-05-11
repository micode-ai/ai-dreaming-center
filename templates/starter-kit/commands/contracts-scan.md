---
description: Scan the repo and write module / page contracts as Markdown.
---

You are running inside Claude Code, spawned by the AI Dreaming Center to
extract architectural contracts from this project's code and write them
into `docs/contracts/`.

A **contract** is a short Markdown description of a module's or page's
public surface — its responsibilities, inputs, outputs, dependencies — so
future agents (and humans) have an authoritative reference to check
against when they change things.

## What you have

- `cwd` is the project repo root.
- Target directory: `docs/contracts/` (already exists — DC created it).
- Env vars: `LEARNING_SESSION_ID`, `DREAMING_API_URL`, `DREAMING_PROJECT_SLUG`.

## What to do

1. **Find the natural unit of contract** for this repo. Sample:
   - For a monorepo: each package or app is a module-level contract.
   - For a service: each top-level module under `src/` / `apps/api/src/modules/`.
   - For a SPA: each major route/page is a page-level contract.
   - For a CLI: each subcommand.

2. **Pick 5–15 units** for the first pass. Quality > quantity.

3. **For each module, write `docs/contracts/{name}.md`:**

   ```markdown
   ---
   kind: module
   module: '{module name — single-quote to stay YAML-safe}'
   status: active            # draft | active | deprecated
   last_review_at: {YYYY-MM-DD}
   ---

   # {module name} — contract

   ## Responsibility
   One paragraph: what this module owns and what it intentionally does NOT.

   ## Public API
   - `path/to/exported.ext::functionName(args)` — short purpose.
   - `path/to/types.ext::TypeName` — what shape.
   - HTTP routes (if any): `GET /foo/:id`, `POST /bar`.

   ## Inputs / outputs
   - Reads: from where (DB tables, other modules, env, files).
   - Writes: to where.

   ## Dependencies
   - `other-module-A` — used for X.
   - `lib/foo` — used for Y.

   ## Invariants
   - Things that MUST hold (auth checks, ordering, idempotency, ...).

   ## Out of scope
   - Things this module deliberately doesn't do (so don't add them here).
   ```

4. **For each major page (if applicable), write `docs/contracts/{page}.md`
   with `kind: page` and a similar structure.**

5. **Don't duplicate** — read existing `docs/contracts/*.md` first; skip
   ones already filed.

6. **YAML escaping** (critical — broken frontmatter is silently dropped):
   - Always single-quote `module`, `page`, and any free-form string.
   - Inside `'...'`, a single quote is doubled (`'don''t'`).
   - Never mix quotes (`module: "foo" — bar` is invalid).

7. **Report back:**

   ```bash
   curl -s -X POST "$DREAMING_API_URL/api/session/finish" \
     -H "Content-Type: application/json" \
     -d "{\"session_id\":\"$LEARNING_SESSION_ID\",\"status\":\"success\"}"
   ```

## Rules

- Do **not** edit code files — only write into `docs/contracts/`.
- Be concrete: quote real filenames, function names, route patterns.
- If a "module" turns out to be empty / 50 lines / not really its own
  unit — skip it rather than write a generic contract.
- Keep each contract under ~80 lines.
