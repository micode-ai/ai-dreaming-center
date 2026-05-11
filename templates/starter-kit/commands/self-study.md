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

2. **Study it carefully.** Spend most of your turns here. Read the agent file
   end-to-end, then look at the repo to ground what the agent claims. Cheap
   things to check: `package.json` / pyproject for the stack, the directory
   structure, any files the agent mentions by name. Don't open every file —
   sample.

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
