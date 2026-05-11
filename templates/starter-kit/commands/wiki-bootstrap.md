---
description: Generate domain wiki pages by scanning the repository structure.
---

You are running inside Claude Code, spawned by the AI Dreaming Center to
populate this project's wiki (`docs/wiki/`) with one Markdown page per
"domain" (subsystem, package, top-level feature).

## What you have

- `cwd` is the project repository root.
- Target directory: `docs/wiki/` (already exists — Dreaming Center created it).
- Env vars from DC:
  - `LEARNING_SESSION_ID` — session id to mark complete at the end.
  - `DREAMING_API_URL` — base URL (typically `http://localhost:8086`).
  - `DREAMING_PROJECT_SLUG` — slug of the project being bootstrapped.

## What to do

1. **Sample the repo** to identify domains. Look at:
   - top-level directories (`apps/`, `packages/`, `src/`, `services/`, etc.)
   - `package.json` / `pyproject.toml` / `Cargo.toml` workspace members
   - `CLAUDE.md` if present — often lists modules
   - `README.md` "Architecture" / "Components" sections

2. **Pick 5–15 domains** (don't go overboard on the first pass). Each domain
   is a coherent unit a new contributor would learn separately. Examples:
   - For a monorepo: each app or package
   - For a service: each top-level module
   - For a SaaS: auth, billing, dashboard, integrations, ...

3. **For each domain, write `docs/wiki/{domain}.md`** with this skeleton:

   ```markdown
   # {Domain name}

   ## What this is
   One paragraph: what this domain owns and why it exists.

   ## Entry points
   - `path/to/main-file.ext` — what this is
   - `path/to/other.ext` — what this is

   ## Key concepts
   - **Concept A** — one sentence.
   - **Concept B** — one sentence.

   ## Cross-references
   - Talks to: `other-domain` via X
   - Used by: `another-domain` for Y

   ## Where to look first
   When debugging or changing this domain, start at `path/to/something.ext`.
   ```

   Aim for ~40–80 lines per page. Be specific to **this** repo — quote real
   filenames and identifiers. If you can't find concrete details for a
   section, drop the section rather than fill with generic prose.

4. **Optional: write an index** at `docs/wiki/README.md` listing all the
   domain pages with one-line summaries each.

5. **Report back** to the Dreaming Center:

   ```bash
   curl -s -X POST "$DREAMING_API_URL/api/session/finish" \
     -H "Content-Type: application/json" \
     -d "{\"session_id\":\"$LEARNING_SESSION_ID\",\"status\":\"success\",\"note_path\":\"docs/wiki/README.md\"}"
   ```

   On error, send `"status":"failed"` with an `"error_message"`.

## Rules

- Do **not** edit files outside `docs/wiki/`.
- Do **not** run installs, migrations, or anything destructive.
- If `docs/wiki/` already has content, **read first, then add only the
  missing domains** — don't overwrite existing pages.
- Keep total time under ~10 minutes for the first pass.
