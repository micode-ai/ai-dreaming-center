---
description: Surface active in-flight work from the repo as plan files with task checklists.
---

You are running inside Claude Code, spawned by the AI Dreaming Center to
turn the repository's implicit "what's in progress right now" into explicit
**plans** with task checklists, stored in `docs/plans/`.

A **plan** is a Markdown file with frontmatter (title, status) and a list
of Markdown checkbox tasks. The DC plans page parses checkboxes to show
progress: `- [x]` is done, `- [ ]` is pending.

## What you have

- `cwd` is the project repo root.
- Target: `docs/plans/` (already exists — DC created it).
- Env vars: `LEARNING_SESSION_ID`, `DREAMING_API_URL`, `DREAMING_PROJECT_SLUG`.

## What to do

1. **Find sources of in-flight work:**
   - Recent commits (`git log --oneline -50`) — themes that span several commits but aren't done yet.
   - `TODO:` / `FIXME:` clusters in code that share a topic.
   - `CLAUDE.md` "in progress" sections.
   - Existing files in `docs/specs/`, `docs/superpowers/plans/`, `docs/roadmap/`.
   - Branch names from `git branch -r` that suggest unfinished features.

2. **Pick 3–7 plans worth tracking.** Each plan should:
   - Have a clear goal (one sentence).
   - Be partially in-flight (some tasks done, some pending) — pure backlog ideas belong in `docs/product-ideas/`, not here.
   - Have visible movement in the codebase (commits or files) to back up the "done" checkboxes.

3. **For each plan, write `docs/plans/{slug}.md`:**

   ```markdown
   ---
   title: '{short plan name — single-quote to stay YAML-safe}'
   status: active           # active | done | paused | dropped
   ---

   # {plan title}

   ## Goal
   One paragraph: what this plan is trying to achieve.

   ## Context
   Where this came from — recent commits, a spec doc, a user request, etc.

   ## Tasks
   - [x] Already-done task (cite the commit or file that landed it)
   - [x] Another done task
   - [ ] Pending task — specific enough to estimate
   - [ ] Another pending task
   - [ ] Final task

   ## Open questions
   - Anything blocking forward motion (decisions, missing inputs).
   ```

4. **Don't duplicate** — read existing `docs/plans/*.md` first.

5. **YAML escaping**: single-quote `title`. Inside `'...'`, double a single
   quote: `'don''t'`. Don't mix quotes.

6. **Report back:**

   ```bash
   curl -s -X POST "$DREAMING_API_URL/api/session/finish" \
     -H "Content-Type: application/json" \
     -d "{\"session_id\":\"$LEARNING_SESSION_ID\",\"status\":\"success\"}"
   ```

## Rules

- Don't invent plans — if the repo doesn't show a partially-done effort,
  write fewer plans (or none) rather than fluff.
- Mark a task `- [x]` only if you can cite the file / commit that
  completed it.
- Don't edit code files. Only write into `docs/plans/`.
- Keep each plan under ~80 lines.
