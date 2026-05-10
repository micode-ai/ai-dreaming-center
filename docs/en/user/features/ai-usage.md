# AI Usage — token and cost analytics

Two pages:
- **Per-project** (`/p/{slug}/ai-usage`) — aggregates for one project.
- **Global** (`/ai-usage`) — cross-project view: top projects by token spend.

## Contents

- [Where the data comes from](#where-the-data-comes-from)
- [Per-project page](#per-project-page)
- [Global page](#global-page)
- [Project ID mapping](#project-id-mapping)
- [If there is no data](#if-there-is-no-data)
- [Cost vs tokens](#cost-vs-tokens)

## Where the data comes from

The source is the JSONL files Claude CLI writes to `~/.claude/projects/<workdir-encoded>/<session>.jsonl`. Each line is one event, and the final events have fields:
- `total_cost_usd` — session cost.
- `usage.input_tokens` — input tokens.
- `usage.output_tokens` — output.
- `usage.cache_read_input_tokens`, `cache_creation_input_tokens` — cache.

DC runs the cron job `ai_usage_ingest` every 5 minutes. It:
1. Scans every JSONL under `claude_projects_dir` (default `~/.claude/projects/`).
2. Parses new/modified ones.
3. Writes to the `ai_usage_events` table: `(project_id, model, input_tokens, output_tokens, cache_read_tokens, cost_usd, ts)`.
4. Maps the JSONL to a DC project via the `cwd` field in the JSONL → `working_dir` in `projects`.

In other words — DC passively collects analytics for Claude. It doesn't matter whether you started the session through DC or manually via the `claude` CLI in a terminal — both end up in the DB.

## Per-project page

Open `/p/{slug}/ai-usage`.

If there is no data (`summary.error` or an empty set) — you'll see:
- Either a red "Ошибка: ..." (Error: ...) (if the parser failed).
- Or "Нет данных. Запусти ingest или подожди следующий тик cron'а." (No data. Run ingest or wait for the next cron tick.)

If there is data — you'll see:

**Top block: 4 cards in a grid.**
- **Last 7d input** — input tokens over the last 7 days.
- **Last 7d output** — output.
- **Last 7d cache (read)** — cache-read (much cheaper than regular input).
- **Last 30d total** — total tokens over 30 days.

All numbers are big and monospaced.

**Table "By model (last 30d)"** — if there are events in 30d:
- model — Claude model name (e.g. `claude-sonnet-4-5`).
- input — tokens.
- output — tokens.
- cache_read — tokens.
- events — number of ingested events (roughly equal to the number of API calls).

Use it when:
- "How many tokens has this project used in the last 7 days?"
- "Which model dominates — sonnet or haiku?"
- "Compare 7d vs 30d — is consumption growing?"

## Global page

Open `/ai-usage` (without `/p/{slug}/`).

Heading "AI Usage — все проекты" (AI Usage — all projects). Same logic as per-project, but:
- The 4 top cards — totals across **all** projects.
- The 4th card — `events total` (instead of "30d total").
- Table "By project (last 30d)" — grouped by project:
  - `project` — slug, clickable (leads to per-project ai-usage). If the slug is `__unmapped__` — that's data from a JSONL that didn't match a DC project.
  - `input`, `output`, `events`.

Use for:
- "Which project consumes the most?"
- "Are there any unmapped events?" (means JSONL exists but `cwd` did not match the registry).

## Project ID mapping

JSONL → project_id mapping:
1. The JSONL provides the `cwd` (Claude session working directory).
2. `cwd` is normalised (lowercase, slashes).
3. Looked up in `projects.working_dir` with the same normalisation.
4. If found — `project_id` is set. If not — `project_id = NULL` (shown as `__unmapped__`).

What to do if `__unmapped__` annoys you:
- Check that `working_dir` in `projects` exactly matches `cwd` in JSONL.
- On Windows pay attention to slashes and case.
- If you switched cwd inside one session — ingest takes the first value.

If you want zero unmapped — make `working_dir` in the registry exactly match Claude's `cwd`.

## If there is no data

Possible causes:
1. **Just started DC** — the ingest cron hasn't fired yet. Wait 5 minutes.
2. **Wrong `claude_projects_dir`** — settings point at the wrong path. Verify that `~/.claude/projects/` actually has JSONLs. (On Windows: `%USERPROFILE%\.claude\projects\`.)
3. **You haven't used the Claude CLI** — no JSONLs. Start any session via DC or in the console — a JSONL appears.
4. **Mapping didn't match** — JSONLs exist but `cwd` doesn't match `working_dir`. All events fall into `__unmapped__`. On `/p/{slug}/ai-usage` it's empty, on `/ai-usage` you'll see an `__unmapped__` row.

Checks:
- Open `/ai-usage` (global). If `events total > 0` there, ingest works.
- If global is empty — the problem is `claude_projects_dir`.
- If global is non-empty but per-project is empty — the problem is the mapping.

## Cost vs tokens

DC stores both tokens and `cost_usd`. The /ai-usage pages in Wave 2.5 show only tokens.

Where to see the cost:
- On orchestration runs — `/p/{slug}/cascade-costs` (if you ran Roman) shows `total_cost_usd` per run.
- In the JSONL of the session itself — `result.total_cost_usd` is in the final event.

In future waves (4+) cost-trend visualisation is planned. For now — raw tokens only.

---

See also:
- [`analytics-extras.md`](analytics-extras.md) — Cascade Costs and other analytics.
- [`settings.md`](settings.md) — `claude_projects_dir`, `ai_usage_*` keys.
- Technical: [`../../features/analytics.md`](../../features/analytics.md), [`../../schema.md#ai_usage_events`](../../schema.md), [`../../services.md`](../../services.md).
