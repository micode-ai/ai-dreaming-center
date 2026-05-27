# AI Metrics: Skills & Agents Breakdown

**Date:** 2026-05-27
**Status:** Approved (design)
**Author:** brainstorming session

## Problem

The AI-usage metrics pages (`/p/{slug}/ai-usage` per project, `/ai-usage` global)
break token usage down by **model**, **daily series**, **main vs subagents**, and
**top sessions**. The user wants two additional cross-sections:

- **By skill** — which skills are invoked and how often.
- **By agent** — which Task subagents (agentType: `frontend`, `general-purpose`,
  `Explore`, …) are used and how much they cost in tokens.

"Agents" here means Task-tool subagents — the same population already summarized
by the existing "main vs subagents" doughnut — not the rotation agents in
`agent_learning_sessions`.

## What the source logs contain (verified)

Events come from `~/.claude/projects/**/*.jsonl`, parsed into `ai_usage_events`
(one row per assistant message that carries token usage), keyed on `message.id`.

- **Skill invocation** — an assistant message contains a `tool_use` content block
  with `name == "Skill"` and `input == {"skill": "<name>"}`. The message also
  carries `usage`, so it is already an `ai_usage_events` row. A single message may
  in principle contain more than one Skill block (parallel tool calls).
  → Honest metric: **invocation frequency** per skill. Token attribution to a
  skill is deliberately NOT attempted — a skill's loaded content is spread across
  the messages that follow its invocation, so per-skill token sums would be
  misleading.
- **Subagent** — each Task subagent streams into
  `…/<session>/subagents/agent-<hash>.jsonl` with a sibling
  `agent-<hash>.meta.json == {"agentType": "...", "description": "..."}`. The
  subagent's token-bearing messages are already ingested into `ai_usage_events`
  (the file walker yields subagent files); the only missing dimension is the
  **agent name**. `agentType` lives in the meta file, not in the jsonl rows.
  → Clean metric: **total tokens + run count** per `agentType`.

## Data model

### 1. `ai_usage_events.agent_name` (new nullable column)

`ALTER TABLE ai_usage_events ADD COLUMN agent_name TEXT`.

Populated during ingest: for a subagent file, resolve `agentType` from the sibling
`meta.json` once per file and stamp it on every row parsed from that file. NULL for
main-session rows. Reuses the token data already collected — no duplication.

The agent breakdown aggregates `WHERE agent_name IS NOT NULL GROUP BY agent_name`.

### 2. `ai_skill_invocations` (new table)

```sql
CREATE TABLE IF NOT EXISTS ai_skill_invocations (
    message_id   TEXT NOT NULL,
    skill_name   TEXT NOT NULL,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    ts           TEXT NOT NULL,
    ts_date      TEXT NOT NULL,
    session_id   TEXT NOT NULL,
    is_sidechain INTEGER NOT NULL DEFAULT 0,
    model        TEXT,
    source_file  TEXT NOT NULL,
    PRIMARY KEY (message_id, skill_name)
);
CREATE INDEX IF NOT EXISTS idx_skill_inv_proj_date
    ON ai_skill_invocations (project_id, ts_date);
CREATE INDEX IF NOT EXISTS idx_skill_inv_name
    ON ai_skill_invocations (skill_name, ts_date);
```

One row per Skill `tool_use` block. PK `(message_id, skill_name)` makes re-reads of
a file tail idempotent and tolerates multiple skills per message. Fields are
denormalized (mirroring how `project_slug`/`project_cwd` are already denormalized
on `ai_usage_events`) so the preset + model filters work without a join back to
`ai_usage_events`.

**Rejected alternative:** a `skill_name` column on `ai_usage_events`. It loses the
multiple-skills-per-message case and conflates two grains (a token-usage event vs a
skill-invocation fact) on one row.

## Parser changes (`dreaming/services/ai_usage_parser.py`)

- **Agent name:** when `is_subagent` is true for a discovered file, read the sibling
  `agent-<hash>.meta.json` → `agentType`. Thread it through so the inserted event
  rows carry `agent_name`. Add `agent_name` to the `INSERT OR IGNORE` column list in
  `_insert_events`.
- **Skills:** add a pure helper `extract_skill_invocations(obj) -> list[dict]` that,
  given a parsed JSONL object, returns one dict per Skill `tool_use` block (skill
  name + the denormalized fields). Called from the ingest loop independently of the
  `usage > 0` gate that `parse_line` applies (Skill messages do carry usage, but the
  extraction must not depend on that). Batch `INSERT OR IGNORE` into
  `ai_skill_invocations`.
- Both run inside the existing incremental ingest, so new tails are picked up
  automatically; `INSERT OR IGNORE` keeps re-reads safe.

## History backfill

The incremental ingest tracks a per-file `byte_offset` and skips files whose size
is unchanged, so already-ingested history will NOT gain `agent_name` or skill rows
on its own. A one-time backfill re-scans every file from offset 0 and:

- for subagent files: `UPDATE ai_usage_events SET agent_name=? WHERE source_file=?`
  (one statement per file);
- for every assistant line: `INSERT OR IGNORE` its Skill blocks into
  `ai_skill_invocations`.

It is idempotent (UPDATE is deterministic, INSERT OR IGNORE dedups). It runs
**automatically once on startup** when `SELECT COUNT(*) FROM ai_skill_invocations`
is 0 — no manual script or UI action. Lives as a function in the parser module and
is invoked from the lifespan/startup path (guarded, non-fatal on error).

## Stats (`dreaming/services/ai_usage_stats.py`)

Add two private aggregators with the same `start/end/project_id/model` signature as
the existing helpers:

- `_by_skill(...)` → `[{skill_name, calls, sessions}]` ordered by `calls DESC`
  (`COUNT(*)` and `COUNT(DISTINCT session_id)` from `ai_skill_invocations`).
- `_by_agent(...)` → `[{agent_name, runs, events, total_tokens, sessions}]` ordered
  by `total_tokens DESC` (from `ai_usage_events WHERE agent_name IS NOT NULL`;
  `runs` = `COUNT(DISTINCT session_id)`).

Both `project_summary` and `global_summary` gain `by_skill` and `by_agent` keys,
honoring the active preset + model filters exactly like `by_model`.

## UI (`project_ai_usage.html`, `global_ai_usage.html`)

Add one new row of two side-by-side cards, styled identically to the existing
"models / sidechain" row:

- **Left — "По скилам (вызовы)" / "By skill (calls)":** horizontal bar chart
  (Chart.js, top ~12 by calls) plus a compact table (skill · calls). Falls back to
  `common.no_data` when empty.
- **Right — "По агентам (токены)" / "By agent (tokens)":** table (agent · runs ·
  tokens) and/or a horizontal bar by tokens, top ~12. Falls back to `common.no_data`.

Identical markup in both templates (they already duplicate the other sections). New
i18n keys added to `messages_ru.json` and `messages_en.json` (RU is source of
truth; EN mirrors; verified by `scripts/check_i18n.py`):
`ai_usage.by_skill`, `ai_usage.by_agent`, `ai_usage.col.calls`,
`ai_usage.col.runs`, `ai_usage.col.skill`, `ai_usage.col.agent`.

## Testing

`scripts/smoke_skill_agent_stats.py` (manual, matches the `smoke_*` convention):
build a temp DB, ingest a fixture session containing a Skill invocation and a
subagent file + meta, then assert `_by_skill` / `_by_agent` and the backfill produce
the expected aggregates. Run after implementation.

## Out of scope

- Per-skill token attribution (intentionally — see above).
- Time-series (daily) breakdown of skills/agents — only totals over the selected
  window in this iteration.
- Cost ($) conversion — the page is token-based throughout.
