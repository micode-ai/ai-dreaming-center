# FAQ

Frequently asked questions about operating AI Dreaming Center.

## Contents

- [Install and run](#install-and-run)
- [Running sessions](#running-sessions)
- [Tech-debt and Product ideas](#tech-debt-and-product-ideas)
- [Cron and scheduling](#cron-and-scheduling)
- [Security and creds](#security-and-creds)
- [Upgrading and moving](#upgrading-and-moving)
- [Difference vs ALC](#difference-vs-alc)

## Install and run

**Q: Which port does DC use by default?**
A: 8086. You can change it via `--port 9000` when starting uvicorn or via the `port` setting.

**Q: How do I stop ai-dreaming-center?**
A: Ctrl+C in the uvicorn window. All running Claude sessions get a signal via the watchdog or are closed by `cancel_remaining_tasks` in lifespan-shutdown.

**Q: How do I run it as a Windows service / systemd?**
A: See `../deployment.md` — there are descriptions for NSSM (Windows), Task Scheduler, and systemd.

**Q: If I reboot the machine — will running sessions survive?**
A: No. The claude subprocesses die with uvicorn. Their DB rows stay in `running` state, and 5 minutes after DC restart the reconcile job will close them as `failed`.

**Q: Can I run DC on one machine and the Claude CLI on another?**
A: No. DC spawns `claude` via the local `asyncio.create_subprocess_exec` — Claude must be on the same machine.

**Q: Are macOS / Linux supported?**
A: Yes. The Windows-specific code (`shutil.which("claude")` picks up `claude.cmd`, KeepAwake) is defensive: on other OSes it does nothing harmful.

**Q: What if I open `/` without `config.yaml`?**
A: Middleware redirects you to `/setup`. All other routes are also redirected, except `/static/*`.

## Running sessions

**Q: How many sessions can run concurrently?**
A: Globally — `max_concurrent` (default 1). Per-project — `per_project_max_concurrent` if set. If the queue is full — the `Start session` button returns 409 or queues.

**Q: What does "session timeout" mean?**
A: The watchdog kills the claude process after `timeout_minutes` minutes from start (default 20). Often it means the agent got stuck in a loop or is waiting for something that never arrives.

**Q: I clicked Kill but the process is still in the logs?**
A: Kill sends terminate, then ~5 seconds later kill -9. If claude's script intercepts the signal — it can take time. Wait up to 30 seconds, then check Task Manager / `ps aux | grep claude`.

**Q: How does the agent know it's in self-study mode?**
A: DC passes it a prompt of the form `/self-study {agent_name}`. The slash command `self-study` lives in `~/.claude/commands/self-study.md` (via agent-team-starter-kit) and describes the task.

**Q: I added a new md file to `.claude/agents/` but it's not in Rotation.**
A: Open `/p/{slug}/rotation` — when the page loads DC scans the filesystem and automatically adds missing agents with `tier=2`. If still missing — check that the file is valid markdown and the name has no spaces.

**Q: Can I pass extra context to the agent?**
A: Via Kanban: add a custom topic with `target_agents`. The nightly cron will mix it into the prompt. See [`features/topics-kanban.md`](features/topics-kanban.md).

**Q: Where do I see the full session stdout after it finishes?**
A: On `/live` — only during streaming. After completion the JSONL stays at `~/.claude/projects/<workdir>/<session>.jsonl` — that's Claude's own file, DC does not duplicate it.

## Tech-debt and Product ideas

**Q: Where do tech-debt items come from?**
A: They are written by the weekly_tech_debt_scan agent into `tech_debt_dir`. The scanner is off by default — you need to enable it (see [`workflows/weekly-scanners.md`](workflows/weekly-scanners.md)).

**Q: Can I create a tech-debt item manually via UI?**
A: No. The UI only closes (`close`) and deletes (`delete`). Creation — via the scanner or by manually editing the md file in `tech_debt_dir`.

**Q: What does close mean on findings?**
A: DC rewrites the frontmatter: `status: closed`. The file stays, in the findings list the item stops showing the `close` button. If you have a status filter — you can hide closed.

**Q: If I delete findings — do I lose the history?**
A: The file is physically removed from disk. If your repo is under git — it stays in history and can be restored via `git restore`.

**Q: Why is there a `→ Jira` button if I could do it manually?**
A: DC takes the title and body from the md file, creates a Jira Task via REST API, and writes the back-link (`jira_ticket: PROJ-123`) into the frontmatter. Fewer chances to forget or typo.

## Cron and scheduling

**Q: Where do I see which cron jobs are registered?**
A: There is no UI page yet. For technical debugging — see [`../troubleshooting.md`](../troubleshooting.md), there's a command to introspect the lifespan.

**Q: How do I change the nightly time?**
A: `/settings` → group "Scheduling — nightly" → key `cron_expression`. Format — standard 5-part cron.

**Q: The cron didn't fire overnight. What do I check?**
A: 1) `cron_enabled = true` (globally and per-project if overridden). 2) `enabled = true` on the project. 3) DC server didn't crash at the cron moment — look at the uvicorn logs. 4) Rotation has at least one agent with `enabled = true`.

**Q: What happens if DC is offline when cron should fire?**
A: The job doesn't run. When DC starts again, the scheduler picks the next tick. There is no backfill for missed runs.

**Q: Can I have a different schedule for different projects?**
A: Yes. On `/p/{slug}/settings` set `cron_expression` to `override`, pick the Override radio button, type your cron — Save.

## Security and creds

**Q: Where is the Jira API token stored?**
A: By default — in `config.yaml` (if you entered it via global settings) or in the `project_settings` table (if via per-project). Better not to commit either file — `config.yaml` should be in `.gitignore`, and `data/dreaming.db` excluded too.

**Q: Can I keep the token in env?**
A: Yes. Pydantic-settings reads env vars with the `DC_` prefix. For example `DC_JIRA_API_TOKEN=...`.

**Q: Does DC send data anywhere itself?**
A: Only to Jira (if you create a ticket) and to Anthropic (when Claude makes API requests). There is no telemetry built into DC.

**Q: Who can reach the UI?**
A: There is no authentication in DC. If you bind to `0.0.0.0:8086` — anyone reachable on the network sees your DB. Use `host = 127.0.0.1` for local-only or close the firewall.

## Upgrading and moving

**Q: How do I upgrade DC?**
A: `git pull && pip install -e .` in the active venv. Restart uvicorn. Schema migrations run idempotently on first connection — you don't need to run them by hand.

**Q: What if I move `data/dreaming.db` to another machine?**
A: Also move `config.yaml` (paths live there) and `~/.claude/projects/<workdir>/...` if you want to keep AI Usage history. On the new machine the paths will be different — fix `working_dir` in the registry.

**Q: How do I reset the DB and start from scratch?**
A: Stop uvicorn, delete `data/dreaming.db` and `data/dreaming.db-wal/.db-shm`, start again. The schema is recreated empty.

## Difference vs ALC

**Q: What's the difference between DC and agent-learning-center?**
A: DC is the multi-project version. ALC works with one project (one `working_dir`); DC handles N projects at once with a registry, an aggregated dashboard, and orchestration. Schema is a fork-greenfield: 14 ALC tables got `project_id`, 2 new ones were added (`projects`, `project_settings`).

**Q: Can I run ALC and DC at the same time?**
A: Yes. They listen on different ports (8085 vs 8086) and have different SQLite DBs (`data/learning.db` vs `data/dreaming.db`). No conflicts.

**Q: Can I migrate data from ALC to DC?**
A: Not automatically. You'd have to do an ETL by hand — export from ALC via SQL, transform (add `project_id`), import into DC. It's a one-off, not documented — file an issue if you need it.

**Q: Is ALC still being developed?**
A: ALC is single-project, baseline, doesn't get new features. All new waves (orchestration, cascade, AI usage) ship to DC only.
