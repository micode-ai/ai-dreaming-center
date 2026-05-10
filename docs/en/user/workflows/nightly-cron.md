# Configuring the nightly cron

Every night DC automatically runs self-study for the top-N agents of every enabled project. Here's how to configure that behaviour.

## Contents

- [How cron picks agents](#how-cron-picks-agents)
- [Key settings](#key-settings)
- [Changing the time](#changing-the-time)
- [Per-project schedule](#per-project-schedule)
- [Temporarily disable](#temporarily-disable)
- [Verify that cron is actually registered](#verify-that-cron-is-actually-registered)

## How cron picks agents

Algorithm of nightly_learning_{slug}:

1. SELECT from `agent_learning_rotation` for the current project_id where `enabled=true`.
2. ORDER BY:
   - `last_studied_at ASC NULLS FIRST` — the never-studied first, then the longest-not-studied.
   - `tier ASC` — on a tie, P1 before P2 before P3.
3. LIMIT `agents_per_night` (default 3).
4. Run those agents one by one (or in parallel if `max_concurrent > 1`):
   - Spawn `claude` with the prompt `{self_study_command} {agent}`.
   - Custom topics for project_id and target_agents — mixed in via env vars / args.
   - Watchdog at `timeout_minutes`.
   - Between launches — a `wait_between_sec` (default 30) pause.
5. After each session ends — update `last_studied_at = now()` for the agent.

Effect: over time every agent gets roughly equal attention, but P1 agents are pulled forward more often when last_studied_at is similar.

## Key settings

All available on `/settings` (global) and `/p/{slug}/settings` (per-project override).

Group **Scheduling — nightly**:

- **`cron_enabled`** (bool, default `true`) — master switch. If false — the cron job is not registered.
- **`cron_expression`** (str, default `0 3 * * *`) — standard 5-part cron. Default — every day at 3:00.
- **`agents_per_night`** (int, default 3) — how many top agents to pick.
- **`wait_between_sec`** (int, default 30) — pause between sessions.
- **`nightly_max_concurrent`** (int, default follows global `max_concurrent`) — concurrency cap specifically for the nightly cron.

Also relevant (group Self-study):
- **`self_study_command`** (str, default `/self-study`) — slash command to invoke.
- **`self_study_max_turns`** (int, default 50).
- **`self_study_model`** (str) — model override.
- **`timeout_minutes`** (int, default 20).

## Changing the time

Cron expression — standard:
```
* * * * *
| | | | |
| | | | +-- day of week (0–6, sunday=0)
| | | +---- month (1–12)
| | +------ day of month (1–31)
| +-------- hour (0–23)
+---------- minute (0–59)
```

Examples:
- `0 3 * * *` — every day at 3:00.
- `0 4 * * 1-5` — weekdays at 4:00.
- `0 2,14 * * *` — every day at 2:00 and 14:00.
- `30 23 * * 0` — Sunday 23:30.

To change:
1. `/settings` → group Scheduling — nightly → key `cron_expression`.
2. Type the new value.
3. Save.

DC re-registers all cron jobs (one per project) with the new expression. The changes take effect on the next scheduler tick (usually a few seconds after Save).

**Note:** the timezone is the DC machine's local time. Not UTC.

## Per-project schedule

If you want one project to study at one time and another at another time:

1. On `/p/{slug-A}/settings` → `cron_expression` → Override → type `0 2 * * *`.
2. On `/p/{slug-B}/settings` → `cron_expression` → Override → type `0 4 * * *`.
3. Save both.

The job ids are different (`nightly_learning_slug-A`, `nightly_learning_slug-B`), so APScheduler triggers them independently.

Similarly you can override `agents_per_night` (one project studies 5 agents, the other — only 1):
- Project A: `agents_per_night = 5`.
- Project B: `agents_per_night = 1`.

## Temporarily disable

Way 1 — globally for everyone:
- `/settings` → `cron_enabled` → uncheck → Save.
- All nightly_learning_* jobs unregister.

Way 2 — per-project:
- `/p/{slug}/settings` → `cron_enabled` → Override → uncheck → Save.
- Only this project stops getting crons.

Way 3 — disable the whole project:
- `/projects` → `Disable` button next to the project.
- The cron job unregisters. The project disappears from the header dropdown.

Way 4 — disable an agent:
- On `/p/{slug}/rotation` toggle `enabled` for the specific agent to `—`.
- The cron job still runs, but this agent is not in the pick.

Way 5 — drop tier:
- Set tier P3 — picked last.
- Not a disable, just deprioritisation.

## Verify that cron is actually registered

There is no UI list of jobs page yet (TODO for a future wave).

**Method 1 — uvicorn logs on startup** (if launched with `--log-level debug`):
- During lifespan startup APScheduler logs: `Adding job tentatively -- it will be properly scheduled when the scheduler starts`. Then `Added job nightly_learning_my-app to job store ... cron(... )`.

**Method 2 — wait**:
- At cron_expression time check `/p/{slug}/`. A session row should appear with status `running`.

**Method 3 — interactive REPL** (if you know your way around the code):
- Open Python inside DC's venv.
- Import and enumerate the scheduler's jobs through app.state. See [`../../troubleshooting.md`](../../troubleshooting.md) — there's a snippet.

**Method 4 — APScheduler jobstore**:
- DC uses MemoryJobStore by default (jobs live only while the process is alive). On restart everything is recreated.
- If you switched to SQLAlchemyJobStore (custom) — look in the DB.

If nothing fires at cron time — typical causes:
- `cron_enabled = false` (global or per-project).
- Project `enabled = false`.
- In rotation every agent has `enabled = false` (no candidates).
- The DC server was off at cron time.
- The machine's timezone is not what you expected.

---

See also:
- [`../features/self-study.md`](../features/self-study.md) — what self-study actually does.
- [`../features/rotation.md`](../features/rotation.md) — managing the agent list.
- [`../features/settings.md`](../features/settings.md) — where to change settings.
- [`weekly-scanners.md`](weekly-scanners.md) — opt-in weekly scanners.
- Technical: [`../../features/self-study.md`](../../features/self-study.md), [`../../services.md#scheduler`](../../services.md).
