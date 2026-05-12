# Glossary

Terms that show up across DC and its documentation. Sorted alphabetically; in parentheses — the English/technical name under which the concept appears in code and UI.

## A–Z core terms

**ALC (Agent Learning Center)** — the single-project predecessor of DC. If you have an ALC instance running somewhere — it does not conflict with DC: different ports, different databases.

**APScheduler** — the scheduler library. DC uses `AsyncIOScheduler`. Technically invisible to the user, but if you see `apscheduler.scheduler` in the logs — that's it.

**Cascade** — a pipeline of 5 phases: contract → design → implementation → review → qa, with a gate-verdict between phases (approve / return-to-stage / reject). Started via orchestration with type `cascade`. More in [`features/cascade.md`](features/cascade.md).

**ClaudeSessionTail** — internal DC component that reads claude's stdout in JSONL format and fans out events to the SSE stream and to orchestrator events. Invisible to the user.

**Claude Code project (vs DC project)** — Claude Code stores its history under `~/.claude/projects/<workdir>/...`. A DC project is a row in the `projects` table mapping slug ↔ working_dir. They are different things: one Claude Code project may or may not be a DC project.

**Claude project dir** — `claude_projects_dir` in settings, default `~/.claude/projects/`. The source from which DC ingests JSONL for AI Usage analytics.

**Cron expression** — a 5-part string like `0 3 * * *` (minute / hour / day / month / day-of-week). Used in `cron_expression`, `weekly_*_cron`. Parsed by APScheduler.

**Custom topic** — a row in the `custom_topics` table, added via Kanban. Mixed into the prompt of the nightly self-study.

**DC (AI Dreaming Center)** — this project. The env-var prefix in code is `DC_`.

**Default project** — the project marked `is_default=true` in the registry. Affects the home page `/` (if there is a default — redirect to its dashboard; otherwise the aggregated one is shown).

**Disable / Enable** — a registry toggle: disabled projects disappear from the header dropdown, their cron jobs auto-unregister, but the data in the DB is preserved.

**Domain (wiki)** — a separate markdown file in `wiki_dir` describing one logical project domain (auth, billing, ui-shell). The count is shown on `/p/{slug}/wiki`.

**Evolution** — a markdown file in the project's `_context/` directory describing override behaviour for an agent (something like a personality patch). Visible on `/p/{slug}/evolutions`.

**Finding (sidecar)** — a JSON report by a reviewer agent (vera/svetlana/silent-failure-hunter) in `sidecar_findings_dir`. Each one is a bag of fields: id, severity, module, file, rule, title.

**Gate verdict** — the orchestrator's decision at a cascade stage boundary: `approve` (move on), `return-to-stage` (return for iteration), `reject` (run fail).

**Inherit / Override** — settings inheritance mechanism. A per-project value in `project_settings` either inherits the global default (inherit) or overrides it (override). See [`features/settings.md`](features/settings.md).

**Jira ticket** — the Jira ticket ID (e.g. `PROJ-1234`). Saved in the frontmatter of the idea md-file after a successful `→ Jira` action.

**Kanban** — the custom topics board, page `/p/{slug}/kanban`. CRUD over the `custom_topics` table.

**Kill (button)** — a POST request to `/p/{slug}/live/kill/{agent}`. Sends terminate to the claude subprocess; the DB row is marked failed.

**KeepAwake** — a Windows-specific service that keeps Modern Standby off while there are running sessions. On macOS/Linux a no-op.

**Locale** — the UI language: `ru` or `en`. Stored in the `dc_locale` cookie. Toggled by the `EN/RU` button in the header.

**Loop** — a markdown file in `loops_dir`. Describes an agent's "reflex-loop" (a repeating self-correcting cycle). On `/p/{slug}/loops` — list with iteration counter.

**Node (orchestrator)** — a node in an orchestration: one agent in a run. Can be root (Orchestrator) or sub-agent. Visible on the run's detail page.

**Note** — a markdown file the agent writes as the result of self-study. Lives in `learning_notes_dir`. The path is recorded in `agent_learning_sessions.note_path`.

**Plan** — a markdown file with a tasks checklist that the Orchestrator writes into `plans_dir`. On the page — a progress bar (`done/total`).

**Process Manager** — internal DC component responsible for spawn/track/kill of all claude subprocesses. Invisible to the user.

**Product idea** — a markdown file in `product_ideas_dir` with frontmatter (id/title/status/priority/jira_ticket). Created by the weekly_product_ideas_scan.

**Project (DC project)** — a row in the `projects` table. Unique slug, label, working_dir, enabled/is_default flags.

**Projects root** — the root directory under which all DC projects live. Default `D:\Work\micode\` or similar.

**Reconcile job** — an interval job that, every 5 minutes, looks at running sessions in the DB and, if the claude process is already dead — closes the row with status `failed`/`timeout`.

**Resume** — orchestration continuation: spawning a new claude subprocess with `--resume {session_id}`. Available for finished runs.

**Orchestrator** — the root orchestrator agent. In code `agent_name="orchestrator"`, `role="orchestrator"`. Started via the form on `/p/{slug}/orchestration`. Previously (before 2026-05-12) called **Roman** — older runs in the DB may still carry `agent_name="roman"`; that's a backwards-compat detail, new code uses the new name everywhere.

**Rotation** — the project's agent list with tier and enabled flag. Used by the nightly cron to pick today's top-N candidates.

**Scheduler** — DC's component wrapping APScheduler. Registers cron jobs for every enabled project.

**Autoconfig (directories)** — one-click mechanism on 8 dashboard pages: creates a sensible default directory (`docs/<feature>/` or `.claude/agents/<feature>/`) and saves the per-project setting. Defaults live in `dreaming/services/autoconfig.py:DEFAULTS`. See [`features/out-of-the-box.md`](features/out-of-the-box.md#directory-autoconfig).

**Orphan (session)** — a row in `agent_learning_sessions` with `status='running'` whose process died without the row being closed. Caused by the Wave-0 reconcile bug. Fixed by the Force-close button on the dashboard.

**Self-study** — the slash command `/self-study {agent}` that makes Claude re-read its agent file and write a note.

**Session (agent learning)** — one self-study attempt. A row in `agent_learning_sessions` (id, project_id, agent_name, status, started_at, finished_at, note_path, error_message).

**Sidecar (reviewer)** — a separate reviewer agent (vera, svetlana, silent-failure-hunter) that writes JSON reports into `sidecar_findings_dir`. Started by slash commands or by the Orchestrator.

**Slash-command** — a command of the form `/{name}` that Claude understands. DC spawns claude with one of these prompts (`/self-study agent`, `/wiki-bootstrap`, etc.).

**Starter-kit** — a set of files under `templates/starter-kit/` in the DC repo that get mirrored into a project's `{working_dir}/.claude/` (slash commands plus skeletons like the weekly checklist). Installed via a UI button on the Rotation/Topics pages or via `scripts/install_starter_kit.py`. See [`features/out-of-the-box.md`](features/out-of-the-box.md#starter-kit).

**Slug** — short machine identifier of a project (`my-app`, `wishlist`, `mi-code-ai`). Unique. Not editable via UI (only via DB).

**SSE (Server-Sent Events)** — a way of pushing live events from server to browser. Used for streaming stdout on `/live` and as a polling replacement on the orchestration detail page.

**Stage (cascade)** — one of the 5 cascade phases: contract, design, implementation, review, qa. Each one is a separate set of nodes.

**Status (session)** — `running` / `success` / `failed` / `timeout`. All are terminal except `running`.

**Subagent** — child claude process, spawned via the Task/Agent tool from the Orchestrator. Visible as a separate node on the orchestration detail page.

**Tech debt** — a markdown file in `tech_debt_dir` with frontmatter (id/title/status/priority/module). Created by the weekly_tech_debt_scan.

**Tier** — an agent's priority in rotation: 1 (high) / 2 (normal, default) / 3 (low). Affects sorting in the nightly cron when picking top-N.

**Topic (weekly checklist)** — an item from weekly-learning-checklist.md (read-only, generated by a starter-kit agent). Visible on `/p/{slug}/topics`.

**Watchdog** — an async task that kills the claude subprocess after `timeout_minutes`.

**Weekly scanner** — opt-in cron jobs of the form `weekly_tech_debt_scan_{slug}`, `weekly_product_ideas_scan_{slug}`, `weekly_wiki_lint_{slug}`. Off by default, enabled via project settings.

**Working dir** — the absolute path to the project folder on disk. One of the key attributes of a `projects` row. Passed as cwd when spawning claude.

If you run into a term that's not here — look at [`../README.md`](../README.md) (it also has a glossary) or [`faq.md`](faq.md).
