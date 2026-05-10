# What is AI Dreaming Center

A short description of the project, its operating model, and its limits.

## Contents

- [Goal](#goal)
- [Conceptual model](#conceptual-model)
- [Navigation](#navigation)
- [Which scenarios it solves](#which-scenarios-it-solves)
- [What DC does NOT do](#what-dc-does-not-do)
- [User-facing limits](#user-facing-limits)

## Goal

AI Dreaming Center (DC) is a single control panel for a team of Claude agents working across multiple projects at once. If you have five-to-ten local repositories and keep your own team of agents in each one via `.claude/agents/` — DC gives you one UI on top of all of it.

What you get out of DC:

- Run nightly self-study runs (the agent reads its instructions, the codebase, and writes a note).
- See the live stream of logs from a running session.
- Read the notes the agents wrote overnight.
- Browse tech-debt and product ideas the agents collected (and turn an idea into a Jira ticket with one click).
- Run the Roman orchestrator against a free-form goal and watch how he decomposes it into subagents.
- Look at analytics — how many tokens and how much money each project consumed.

DC replaces a hell of opaque n8n workflows and `cron` scripts with one FastAPI page.

## Conceptual model

The main entities:

- **Project** — one folder under `projects_root`. For example, if `projects_root = D:\Work\micode\`, then `D:\Work\micode\my-app\` is one project and `D:\Work\micode\wishlist\` is a second one. Each project has its own `.claude/agents/` directory with agents and its own learning statistics in the DC database.
- **Agent** — one markdown file at `.claude/agents/{agent-name}.md` inside a project. Describes Claude's behaviour.
- **Session** — one launch of the Claude CLI in self-study mode for one agent. The session has a status (success / failed / timeout), a duration and an optional path to the note.
- **Run** (orchestration run) — a Roman orchestration: one goal, a tree of root agent and subagents.
- **Cascade** — a structured run with phases contract → design → implementation → review → qa and gate-verdicts between them.

All entities are isolated between projects. Deleting a project cascades and removes all of its history.

## Navigation

- Root `/` — aggregated dashboard across all enabled projects: top-line metrics (success/failed/timeout for the week, running right now, total tech-debt, total ideas) + project cards.
- `/projects` — project registry: list table, `Disable` / `Delete` buttons, a "Scan and import new" form.
- `/p/{slug}/` — dashboard for a specific project: its metrics, recent sessions, active runs.
- `/p/{slug}/{section}` — specific sections (orchestration, live, rotation, topics, kanban, notes, findings, tech-debt, ideas, wiki, ai-usage, evolutions, loops, plans, cascade-costs, contracts, sidecar-findings, settings).
- `/settings` — global settings (~92 keys across 13 groups).
- `/p/{slug}/settings` — per-project overrides on top of the global ones.

The header always carries a `<select>` with a list of all projects: switch quickly. The `EN/RU` button on the right toggles the UI language.

## Which scenarios it solves

- **Nightly self-study**: every night the cron picks the top-N agents from rotation with the oldest `last_studied_at` and runs them in order. By morning your dashboard has a fresh list of notes.
- **Manual agent run**: you urgently need some agent to re-read its instructions — open the project's rotation, press `Start session` next to it, wait.
- **Tech-debt review**: a weekly scanner has written a dozen markdown files into `tech_debt_dir`; you open `findings`, see the list, click into something interesting, scroll — close or delete.
- **Idea → Jira**: you spot a good idea in product_ideas, press `→ Jira`, the ticket gets created in your Jira project.
- **Orchestrating a goal**: "decompose feature X for module Y" — type that into the form on `/p/{slug}/orchestration`, Roman starts a run, on the detail page you watch subagents and their messages appear.
- **Cost analytics**: open `/ai-usage` (global) or `/p/{slug}/ai-usage` — see tokens/cost per model and per project.

## What DC does NOT do

To set the right expectations — DC is a **control panel**, not a code editor and not a CI server:

- DC **does not edit** your code. Code mods are done by Claude inside its sessions.
- DC **does not run tests**. Claude does (if you ask), or your CI.
- DC **does not manage deploys**. There are no "Deploy to prod" buttons.
- DC **does not aggregate git history and does not open PRs**. That's Claude via its tool-uses.
- DC **does not store agent code**. Agents live in `.claude/agents/` of your projects; DC only invokes them via slash commands.
- DC **does not edit** your markdown artifacts (tech-debt, ideas) itself — it only reads them and rewrites frontmatter (`status: closed`, `jira_ticket: ABC-123`). The body content stays untouched.

## User-facing limits

- **One claude process per agent-project**: trying to start a second session for the same agent in the same project gets rejected with "already running".
- **Global concurrency limit**: `max_concurrent` (default 1) — even if you press `Start session` for three agents in different projects, they queue up.
- **Per-project limit**: optional, overridable via settings.
- **Watchdog**: every session is bounded by `timeout_minutes` (default 20). You can't do long tasks via self-study — it's for short review sessions.
- **One Roman per project**: trying to start a second orchestration run while the first is running redirects to the existing one.

If you want a deeper look at how DC works under the hood — open [`../architecture.md`](../architecture.md).
