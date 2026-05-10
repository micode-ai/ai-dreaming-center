# Weekly scanners

In addition to the daily self-study, DC can run weekly "scanner" agents that analyse the project as a whole and write analytics as markdown files:
- **Tech-debt scanner** — walks the code, looks for technical debt, writes md files into `tech_debt_dir`.
- **Product ideas scanner** — analyses features / pain-points, writes ideas into `product_ideas_dir`.
- **Wiki linter** — checks wiki domains, updates/adds.

By default all three are **off** (opt-in). Here's how to turn them on.

## Contents

- [Why weekly](#why-weekly)
- [Scanner list](#scanner-list)
- [Enable a scanner](#enable-a-scanner)
- [Cron-expression configuration](#cron-expression-configuration)
- [Manual trigger](#manual-trigger)
- [What the scanner does inside](#what-the-scanner-does-inside)

## Why weekly

Self-study every night = "studying an agent's area of responsibility". Useful, but doesn't cover:
- Whole-project analysis in one pass.
- Cross-cutting problems (tech debt scattered across modules).
- Systematic generation of an ideas backlog.

A weekly scanner is a different genre: one agent, one task, one big sweep over the entire project, output — a structured markdown catalogue.

## Scanner list

### `weekly_tech_debt_scan_{slug}`

Runs the agent that scans the code and writes md files into `tech_debt_dir`. Each file = one tech-debt item with frontmatter (id, title, status, priority, module).

Default agent — `tech-debt-scanner` or `td-scanner` (in your starter kit's `.claude/agents/`). Configurable via `weekly_tech_debt_scan_agent`.

### `weekly_product_ideas_scan_{slug}`

Runs the agent that analyses UX / feature gaps / user pain and writes md files into `product_ideas_dir`. Each = one idea with frontmatter (id, title, status, priority, jira_ticket).

Default agent — `product-ideas-generator` or similar. Configurable via `weekly_product_ideas_scan_agent`.

### `weekly_wiki_lint_{slug}`

Runs the agent that checks the wiki:
- Are all domains covered.
- Did some modules disappear after code changes.
- Stylistic issues.

Writes/updates md files in `wiki_dir`. Configurable via `weekly_wiki_lint_agent`.

## Enable a scanner

Take tech-debt as the example. Other scanners — same pattern.

1. Open `/p/{slug}/settings`.
2. Scroll to the group "Scheduling — weekly (opt-in)".
3. Find the key `weekly_tech_debt_scan_enabled`. By default it inherits from global (also `false`).
4. Click the `Override` radio. A checkbox appears.
5. Tick the checkbox.
6. While here, make sure `tech_debt_dir` is set (override or inherit from global). If global is empty — type the absolute path.
7. Save.

After Save:
- The scheduler re-registers jobs. A new `weekly_tech_debt_scan_{slug}` appears.
- On the next cron tick (per `weekly_tech_debt_scan_cron`, default `0 4 * * 0` — Sunday 4:00) the job fires.
- It creates or updates md files in `tech_debt_dir`.
- On `/p/{slug}/findings` you see items.

## Cron-expression configuration

Same 5-part cron as in [`nightly-cron.md`](nightly-cron.md). Defaults:
- `weekly_tech_debt_scan_cron = 0 4 * * 0` — Sunday 4am.
- `weekly_product_ideas_scan_cron = 30 4 * * 0` — Sunday 4:30.
- `weekly_wiki_lint_cron = 0 5 * * 0` — Sunday 5am.

Offsets of 30 min avoid running everything at once (avoid peak load on the Anthropic API).

To change:
- `/settings` (global) or `/p/{slug}/settings` (per-project).
- Group Scheduling — weekly.
- Key `weekly_*_cron` → type the new value.
- Save.

If you want every other week instead of weekly — that's harder. Cron doesn't natively support "every other week". Workaround: run every Sunday, but in the scanner agent itself (the slash-command) add logic "if I already scanned this week — exit".

## Manual trigger

Want to run the scanner now without waiting for cron?

The UI has **no direct button** for tech-debt and product-ideas scanners. Workarounds:

**Way 1: via `/p/{slug}/orchestration`**
- Type a goal like `Run tech-debt scan now` (or with an explicit phrasing of the scanner agent's task).
- `Start Roman`.
- Roman picks up the task and runs the suggested agent.

Not perfect (Roman adds overhead), but it works.

**Way 2: via `Start session` on rotation**
- If the scanner agent exists as an md file in `.claude/agents/` (e.g. `tech-debt-scanner.md`) — it'll show up in Rotation.
- Click `Start session` next to it.
- That starts a regular self-study (not the weekly_*_scan job), but the effect is the same — the scanner agent runs.

**Way 3: via `Run /wiki-bootstrap` (wiki only)**
- The button right on `/p/{slug}/wiki`. See [`../features/wiki.md`](../features/wiki.md).

**Way 4: manual cron tick** (advanced)
- If you're a developer — call the scanner job function directly via REPL. See `dreaming/services/scheduler.py`.

## What the scanner does inside

Technically weekly_tech_debt_scan_{slug} is an APScheduler job that, when triggered:

1. Gets project_id from the job name.
2. Resolves `weekly_tech_debt_scan_agent` (default `tech-debt-scanner`) and `weekly_tech_debt_scan_command` (default `/tech-debt-scan`).
3. Spawns `claude` with the slash-command and `cwd={working_dir}`.
4. Creates a session row in DB with `agent_name='_weekly-tech-debt-scan'`.
5. Watchdog at `timeout_minutes` (but typically scanners run longer — might be worth bumping to 60).
6. On completion — the sessions row is marked success/failed.

The `/tech-debt-scan` slash command (in `~/.claude/commands/tech-debt-scan.md`) describes what to do:
- Read the whole code.
- Compare with previous findings (avoid duplicates).
- Write new md files into `tech_debt_dir`.
- Close old findings that are no longer relevant.

Exact behaviour depends on your starter kit. If you don't have such a slash command — you need to write one.

---

See also:
- [`nightly-cron.md`](nightly-cron.md) — daily self-study schedule.
- [`../features/tech-debt.md`](../features/tech-debt.md) — where to see tech-debt scan results.
- [`../features/ideas.md`](../features/ideas.md) — where product ideas land.
- [`../features/wiki.md`](../features/wiki.md) — where wiki status lives.
- [`../features/settings.md`](../features/settings.md) — where to enable.
- Technical: [`../../features/pipelines.md`](../../features/pipelines.md), [`../../services.md#scheduler`](../../services.md).
