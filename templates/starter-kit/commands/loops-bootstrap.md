---
description: Document the project's recurring operational loops as markdown files.
---

You are running inside Claude Code, spawned by the AI Dreaming Center to
identify and document **loops** — recurring processes the team runs
(CI/CD, release, deploy, on-call, weekly reviews, retros, …) — as
markdown files in `docs/loops/`.

A **loop** is a description of a self-correcting cycle: trigger → steps →
checkpoint → repeat. The DC loops page parses frontmatter (title, status,
iterations) and shows it in a table.

## What you have

- `cwd` is the project repo root.
- Target: `docs/loops/` (already exists — DC created it).
- Env vars: `LEARNING_SESSION_ID`, `DREAMING_API_URL`, `DREAMING_PROJECT_SLUG`.

## What to do

1. **Find sources of cyclic processes:**
   - `.github/workflows/*.yml` — CI/CD loops.
   - `package.json` scripts that look like cron-like jobs.
   - `docker-compose.yml`, `scripts/`, `bin/`, `Makefile` targets.
   - `README.md` / `CLAUDE.md` "Release process" / "Deploy" / "Weekly" sections.
   - Cron files: `crontab`, `.cron`, `pyproject.toml` task runners.

2. **Pick 3–7 loops worth documenting.** A loop is worth a file when:
   - It runs more than once (not a one-off task).
   - It has a clear trigger.
   - It can fail and someone has to retry / debug.

3. **For each loop, write `docs/loops/{slug}.md`:**

   ```markdown
   ---
   title: '{short loop name — single-quote to stay YAML-safe}'
   status: running          # running | paused | done | broken
   iterations: 0            # integer; estimate or 0 if unknown
   ---

   # {loop title}

   ## Trigger
   What kicks this off — cron expression, git event, manual button,
   release tag, ...

   ## Steps
   1. Step one (cite file/script involved).
   2. Step two.
   3. Step three.

   ## Failure modes
   - What can go wrong, and what to do (rerun, fix X, escalate).

   ## Owner
   Who's responsible (team or person, if known from the repo).

   ## Where to look first when it breaks
   Logs path, dashboard URL, key file to inspect.
   ```

4. **Don't duplicate** — read existing `docs/loops/*.md` first.

5. **YAML escaping**: single-quote `title`. `iterations` is a plain int —
   no quoting needed.

6. **Report back:**

   ```bash
   curl -s -X POST "$DREAMING_API_URL/api/session/finish" \
     -H "Content-Type: application/json" \
     -d "{\"session_id\":\"$LEARNING_SESSION_ID\",\"status\":\"success\"}"
   ```

## Rules

- Don't invent loops — if the repo has no CI, no cron, no release
  process documented, write fewer loops (or none).
- Cite concrete files: `.github/workflows/test.yml`, `scripts/deploy.sh`.
- Don't edit code files. Only write into `docs/loops/`.
- Keep each loop under ~80 lines.
