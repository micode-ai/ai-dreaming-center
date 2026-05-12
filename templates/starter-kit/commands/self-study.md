---
description: Re-read an agent's instructions, summarise, and write a learning note.
argument-hint: <agent-name>
---

You are running inside Claude Code, spawned by the AI Dreaming Center as a
self-study session for the agent **$ARGUMENTS**. Your job is *not* to make
edits to the codebase — only to study the agent file, write a short note,
and report back.

## Context provided by the Dreaming Center

Your `cwd` is the project repo root. The following env vars are set:

- `LEARNING_SESSION_ID` — DB row id for this session (use this when reporting back).
- `LEARNING_AGENT_NAME` — same as `$ARGUMENTS`.
- `LEARNING_PROJECT_SLUG`, `LEARNING_PROJECT_ID`.
- `DREAMING_API_URL` — base URL of the dashboard (typically `http://localhost:8086`).

## What to do

1. **Read `.claude/agents/$ARGUMENTS.md`** (or `.claude/agents/$ARGUMENTS/agent.md`
   if it's a multi-file agent). If neither exists, jump to step 4 and report
   `status="failed"` with `error_message="agent file not found"`.

2. **Study it carefully — but stay within a tight investigation budget.**
   Read the agent file end-to-end, then sample the repo. Hard limit:
   **no more than 6–8 file/grep/glob operations total** before you start
   writing the note. After that, switch to drafting.

   What to look at: `package.json` / `pyproject.toml` / `tsconfig.json` for
   the stack, a top-level directory listing, and 2–3 files the agent
   mentions by name. That's enough.

   **If a file the agent references is missing** (renamed, deleted, moved
   to git history):
   - Don't spend turns hunting it across the repo — single `glob` to confirm
     absence, then **note it under "Agent file issues"** in step 3 below
     and move on.
   - Don't switch to git-history archaeology (`git log --all`, branches,
     etc.). The agent file lying about current state IS the finding.

   The goal is a finished note, not a perfect map of the repo. A short
   accurate note beats a long-running investigation that never reports.

3. **Write a Markdown note** to
   `.claude/agents/learning-notes/{today}-$ARGUMENTS.md`, where `{today}` is
   today's date in `YYYY-MM-DD` form. Create the directory if it doesn't
   exist. Sections (keep the whole file under ~150 lines, no fluff):

   - **Role** — one sentence describing what this agent is for.
   - **Watchlist** — 3–5 concrete things you'd look for in *this* repo if
     someone invoked this agent. Repo-specific, not generic advice.
   - **Clarifying question** — one question you'd ask the user before
     making non-trivial changes through this agent.
   - **Agent file issues** — bullets: anything in the agent file that looks
     out-of-date, contradictory, or missing a guard-rail. Or "none".

3b. **For each Agent file issue, write an Evolution proposal** to
    `.claude/agents/_context/$ARGUMENTS/{today}-{topic-slug}.md`. Create the
    `_context/$ARGUMENTS/` directory if missing. Use kebab-case for the topic
    slug (e.g. `module-count-stale`, `paywall-guard-missing`).

    Format (YAML frontmatter — always single-quote `title`, see the
    YAML escaping note in `/product-idea-scan` if it bites you):

    ```markdown
    ---
    agent: $ARGUMENTS
    title: 'short imperative one-line description of the change'
    status: proposed
    conflict: false
    created_at: {today}
    ---

    ## What's wrong
    One paragraph describing the discrepancy. Be concrete — quote file
    paths and identifiers.

    ## Proposed change
    3–5 bullets describing what to add/remove/change in
    `.claude/agents/$ARGUMENTS.md`. Be specific enough that a human can
    apply this in <5 minutes.

    ## Rationale
    One paragraph: what breaks today, what gets better after the change.
    ```

    Skip evolution proposals when the issue is trivially small (a typo,
    a one-word change) — those belong in the note's "Agent file issues"
    section as a bullet, not as their own file. Evolutions are for
    *structural* misalignments worth reviewing separately.

    If no issues were found in step 3 ("none"), skip this step entirely.

4. **Report back to the Dreaming Center.** Use the Bash tool:

   ```bash
   curl -s -X POST "$DREAMING_API_URL/api/session/finish" \
     -H "Content-Type: application/json" \
     -d "{\"session_id\":\"$LEARNING_SESSION_ID\",\"status\":\"success\",\"note_path\":\"<relative path to the note you wrote>\"}"
   ```

   `<relative path>` is relative to `cwd`, e.g.
   `.claude/agents/learning-notes/2026-05-11-aba-architect.md`.

   On failure, send `"status":"failed"` and an `"error_message"` field
   instead of `note_path`.

## Rules

- Do not edit any file outside `.claude/agents/learning-notes/`.
- Do not run package installs, migrations, or anything destructive.
- If you find yourself wanting to "fix" the agent file, *don't* — write
  that observation under **Agent file issues** in the note and stop.
- One agent per session. Don't recurse into other agents.
