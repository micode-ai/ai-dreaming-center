---
description: Propose 5–10 learning topics for project agents and post them to the AI Dreaming Center.
---

You are running inside Claude Code, spawned by the AI Dreaming Center
(weekly scanner or on-demand) to propose 5–10 learning topics that the
project's agents should study during nightly `/self-study` runs.

## What you have

- `cwd` is the project repository root.
- Env vars: `LEARNING_SESSION_ID`, `DREAMING_API_URL`, `DREAMING_PROJECT_SLUG`.
- Agent roster: every `.md` file in `.claude/agents/` is an agent name. Use the **filename without `.md`** when filling `target_agents`.
- Recent activity signals (cheap to read):
  - `git log --oneline -50` — what's been changing.
  - `.claude/agents/learning-notes/` (if present) — what's been studied recently; avoid duplicating.
  - `.claude/agents/sidecar-findings/` (if present) — open questions agents have flagged.
  - `CLAUDE.md`, `README.md` — current focus areas.

## What to do

1. **Read what's already proposed.** Skip duplicates by title:

   ```bash
   curl -s "$DREAMING_API_URL/api/p/$DREAMING_PROJECT_SLUG/topics/list"
   ```

   This returns a JSON array of active topics. Treat case-insensitive
   exact-title matches as duplicates. Near-duplicates are fine — humans
   prune them later.

2. **Propose 5–10 new topics.** Each topic should be:
   - **Actionable** — a real thing an agent can study in one session.
   - **Targeted** — name 1-3 agents whose role fits. `target_agents` is a
     comma-separated list of agent filenames (no `.md`). Empty string = all.
   - **Grounded** — refer to specific files / modules / commits when possible.

3. **POST each topic** to the ingest endpoint:

   ```bash
   curl -s -X POST "$DREAMING_API_URL/api/p/$DREAMING_PROJECT_SLUG/topics/ingest" \
     -H "Content-Type: application/json" \
     -d '{
       "title": "Refactor session management — переход на FastAPI DI",
       "module": "auth",
       "target_agents": "vera,svetlana",
       "question": "Какие 3 main pain-points у текущей auth.login()?",
       "why_important": "Через 2 недели начинается переписывание; до этого нужна inventory pain-points."
     }'
   ```

   Expected: HTTP 201 with `{"id":"<uuid>"}`. Log and continue on any
   non-2xx response — partial ingestion is acceptable.

   **JSON escaping (critical):** wrap the body in single quotes for the
   shell, and double-quote string values inside JSON. If a value contains
   a literal double quote, use `\"`. Don't mix quote styles.

4. **Report back** when done (success or fail):

   ```bash
   curl -s -X POST "$DREAMING_API_URL/api/session/finish" \
     -H "Content-Type: application/json" \
     -d "{\"session_id\":\"$LEARNING_SESSION_ID\",\"status\":\"success\"}"
   ```

   On failure, send `"status":"failed"` with `"error_message"`.

## Rules

- Do **not** edit any project files. This command is read-only on disk;
  all output goes via the ingest endpoint.
- Do **not** invent topics where none exist — if you can't find 5 real
  things to learn, post fewer.
- Use agent filenames (without `.md`) verbatim in `target_agents`. If
  unsure, leave empty (= all agents).
