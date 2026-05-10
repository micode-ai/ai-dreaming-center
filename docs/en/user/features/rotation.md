# Agent rotation

`/p/{slug}/rotation` — a table with the list of every agent in the project. Here you control who the crontab picks at night, what priority each one has, and you can start any of them manually.

## Contents

- [Opening the page](#opening-the-page)
- [What the table shows](#what-the-table-shows)
- [Where agents come from](#where-agents-come-from)
- [Changing tier](#changing-tier)
- [Toggle enabled](#toggle-enabled)
- [Start session (button)](#start-session-button)
- [If there are no agents](#if-there-are-no-agents)

## Opening the page

From the project header, click the `Ротация` (`Rotation`) tab. URL: `/p/{slug}/rotation`.

On first open DC scans the folder `{working_dir}/.claude/agents/`, finds every md file, and automatically creates an `agent_learning_rotation` row for each with `tier=2`, `enabled=true`. This is the sync: new files land in the DB on the next visit.

## What the table shows

At the top a line like: "N agents in DB; M on disk in {working_dir}/.claude/agents/".

If N = M — synced. If N < M — someone added an md file outside DC and hasn't opened rotation yet. After opening the page — synced.

Columns:
- **agent** — agent name (without `.md`), monospace.
- **tier** — `<select>` with three options: `P1` / `P2` / `P3`. Current value selected.
- **enabled** — toggle button: `✓` if enabled, `—` if disabled.
- **last_studied** — timestamp of the last successful self-study session or `—` if never.
- (last column) — `Start session` button (blue) or `running…` text (amber) if already running.

## Where agents come from

Paths:
1. **Filesystem scan** — DC scans `{working_dir}/.claude/agents/*.md` every time the page is opened. The filename without extension becomes `agent_name`.
2. **Creating a new row** — if such `(project_id, agent_name)` is not in the DB, it's added with tier=2.
3. **Deletion** — if the md file is removed from disk, the DB row stays (but is not shown in the table because it's filtered by filesystem). To delete forever — DELETE directly in the DB.

If you want an agent to appear in DC:
- Create the file `D:\Work\micode\my-app\.claude\agents\my-agent.md`.
- Add at least a heading and a description.
- Open `/p/my-app/rotation` — you'll see it.

Names in DC must match the filenames **exactly** (case-sensitive on Linux/macOS).

## Changing tier

Tier defines an agent's priority in the nightly cron:
- **P1 (high)** — high priority. Picked first when `last_studied_at` ties.
- **P2 (normal, default)** — normal priority.
- **P3 (low)** — low. Only if no P1/P2 candidates.

The nightly cron algorithm: `ORDER BY last_studied_at ASC NULLS FIRST, tier ASC`. That is:
1. First — those never studied at all (NULL last_studied_at).
2. Then the longest-not-studied.
3. On ties — P1 before P2 before P3.

How to change:
1. In the `tier` column click the `<select>`.
2. Pick `P1` / `P2` / `P3`.
3. The form auto-submits (`onchange="this.form.submit()"`). The page reloads with the new value.

There is no Save button — each change is saved instantly.

## Toggle enabled

If `enabled = ✓` — the agent is eligible for the nightly cron's pick.
If `enabled = —` — the cron skips it. But manual `Start session` still works.

To toggle:
1. Click the button with `✓` or `—`.
2. POST to `/p/{slug}/rotation/toggle` is sent.
3. The page reloads with the new value.

Use disable when:
- The agent is broken and its notes are garbage.
- You temporarily don't want to spend tokens on this agent.
- The agent is being refactored and self-study would give false insights.

## Start session (button)

The blue `Start session` button next to an agent — POST to `/p/{slug}/rotation/start/{agent}`.

What happens:
1. DC checks whether a session is already running for this agent in this project. If yes — returns 409.
2. Creates an `agent_learning_sessions` row with status `running`.
3. Resolves claude_path (on Windows picks up `claude.cmd`).
4. Spawns claude with the command `{self_study_command} {agent}`.
5. Starts a watchdog for `timeout_minutes`.
6. Subscribes the live-log streamer to stdout.
7. Redirects the browser to `/p/{slug}/live`.

From there — see [`live-log.md`](live-log.md).

If at click time the global `max_concurrent` is reached — DC returns an error (you have to wait).

## If there are no agents

Scenario: you just created the project and there is no `.claude/agents/`.

On the rotation page you'll see an empty table and the line "0 agents in DB; 0 on disk in {working_dir}/.claude/agents/".

What to do:
1. Create the folder: `mkdir D:\Work\micode\my-app\.claude\agents`
2. Drop at least one md: `echo "# Test agent" > D:\Work\micode\my-app\.claude\agents\test.md`
3. Refresh the page — the agent appears.

Alternative: use agent-team-starter-kit. That's a separate repository with a ready-to-go set of agents (vera, svetlana, silent-failure-hunter, etc.) — clone it on top of your project and you get the full set right away.

---

See also:
- [`self-study.md`](self-study.md) — what these sessions actually do.
- [`live-log.md`](live-log.md) — watching a running session.
- [`../workflows/nightly-cron.md`](../workflows/nightly-cron.md) — how the nightly pick uses tier.
- Technical: [`../../features/self-study.md`](../../features/self-study.md), [`../../schema.md`](../../schema.md).
