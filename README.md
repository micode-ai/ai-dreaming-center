# AI Dreaming Center

Multi-project FastAPI dashboard that orchestrates Claude CLI agent teams across many local projects from a single UI. Fork of [agent-learning-center](https://github.com/RsCloud2022/agent-learning-center) extended with first-class multi-project support.

## What it does

Point AI Dreaming Center at a directory full of projects (default: `D:\Work\micode`). For each project that contains a `.claude/agents/` folder, the center provides:

- **Daily nightly self-study** — agents pick top-N candidates, run via `claude` CLI, results recorded.
- **Live log streaming (SSE)** — watch session stdout in real time; Kill button.
- **Rotation table** — view, tier, enable/disable agents; Start session manually.
- **Tech-debt pipeline** — list, detail, close/delete TD items per project.
- **Product Ideas → Jira** — one-click Task creation from an idea.
- **Wiki bootstrap** — trigger `/wiki-bootstrap` slash command per project.
- **Cron jobs per project** — `nightly_learning_{slug}` plus optional `weekly_tech_debt_scan_{slug}`, `weekly_product_ideas_scan_{slug}`, `weekly_wiki_lint_{slug}`.

Switch between projects via the header dropdown. Drop-in adding a new project: scan or hand-register from `/projects`.

## Quickstart

```bash
git clone <repo-url>
cd ai-dreaming-center
python -m venv .venv
source .venv/Scripts/activate    # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e .
python -m uvicorn dreaming.main:app --port 8086
```

Open http://localhost:8086 — the setup wizard will scan your `projects_root` and let you pick which directories to register.

## Configuration

`config.yaml` holds global defaults (claude_path, projects_root, port, etc.). Per-project overrides live in the `project_settings` table and are editable via `/p/{slug}/settings`. Inheritance: project override → global default → built-in default.

Required for full functionality:
- `claude` CLI installed and on PATH (the `claude_path` resolver picks `claude.cmd` on Windows).
- For Jira integration: set `jira_email`, `jira_api_token`, `jira_user_account_id`, `jira_project_key` (per project or global).

## Architecture

- **Backend:** FastAPI + Uvicorn, async SQLite via `aiosqlite` (WAL mode).
- **Scheduler:** APScheduler (AsyncIOScheduler), per-project cron job IDs.
- **Process model:** `asyncio.subprocess` spawns `claude` CLI; stdout ring-buffer fan-outs to SSE subscribers; KeepAwake suppresses Windows Modern Standby while sessions run.
- **Routing:** `/p/{slug}/...` resolves project via middleware. Cross-project root `/` aggregates per-project metrics.
- **i18n:** lightweight JSON loader with CLDR Russian plurals; `t()` Jinja filter.

Schema is greenfield-forked from agent-learning-center: 14 ALC tables get a `project_id` column, plus 2 new tables (`projects`, `project_settings`).

## Status

Implemented through Wave 2.5:
- Wave 0 — Foundation
- Wave 1 — Self-study core (per-project dashboard, live log, rotation, sessions API, nightly cron)
- Wave 2 — Pipeline pages (topics, kanban, notes, findings, tech-debt, ideas, wiki, weekly crons)
- Wave 2.5 — Tech-debt detail + close/delete; Jira service + Ideas→Jira; Wiki bootstrap button
- Wave 5 — Aggregated cross-project dashboard

Deferred to later waves:
- Wave 3 — Orchestration (Roman live graph, cascade pipelines, harness integration)
- Wave 4 — Team-state (evolutions, loops, plans, AI usage, cascade costs)

## License

(Add LICENSE file at the org level — defaults pending.)
