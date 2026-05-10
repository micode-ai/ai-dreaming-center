# Self-study

Self-study is an automatic mode where Claude re-reads its agent file and writes a note-update on its area of responsibility. Think "agent grokking": the model spends 20 minutes "studying" its role and the codebase.

## Contents

- [What self-study does](#what-self-study-does)
- [How to start manually](#how-to-start-manually)
- [How it starts automatically](#how-it-starts-automatically)
- [Session lifecycle](#session-lifecycle)
- [Where to see the results](#where-to-see-the-results)
- [When the session fails](#when-the-session-fails)
- [Customisation](#customisation)

## What self-study does

When you tell DC "run self-study for agent `vera`", DC spawns the Claude CLI with this command:

```
claude /self-study vera
```

`/self-study` is a slash command pre-installed in `~/.claude/commands/self-study.md` (via agent-team-starter-kit or by hand). It instructs Claude to:
1. Read `.claude/agents/vera.md` (where the area of responsibility is described).
2. Read the relevant parts of the codebase.
3. Mix in active `custom_topics` (if any, for this agent) — DC injects them via template variables.
4. Write a markdown note to `learning_notes_dir` (default `.claude/agents/learning-notes/{date}-{agent}.md`).
5. Optionally — update some tech-debt items, write new ideas, refresh the wiki.

The exact behaviour depends on how `/self-study` is written in your starter-kit.

## How to start manually

1. Open `/p/{slug}/rotation`.
2. Find the agent in the table.
3. If next to it there's a `Start session` button (blue) — click. If it says `running…` — a session is already running.
4. You're redirected to `/p/{slug}/live` with the streaming log.

For a manual run the agent doesn't need `enabled=true` — `Start session` works regardless.

## How it starts automatically

Every night the cron job `nightly_learning_{slug}` (default 03:00) does:
1. Picks every agent in the project's rotation where `enabled=true`.
2. Sorts by `last_studied_at ASC` (oldest first), tiebreak by `tier ASC`.
3. Takes top-N (`agents_per_night`, default 3).
4. Runs them in sequence, waiting `wait_between_sec` (default 30) between sessions.

If the global `max_concurrent` > 1 — they may run in parallel. Default = 1.

To:
- **Change the cron time**: `/settings` or `/p/{slug}/settings` → group "Scheduling — nightly" → `cron_expression`.
- **Change the number of agents per night**: `agents_per_night` in the same place.
- **Temporarily disable**: `cron_enabled = false` (at the global or per-project level).

More — [`../workflows/nightly-cron.md`](../workflows/nightly-cron.md).

## Session lifecycle

```
[user clicks Start session]
        |
        v
+------------------+
| pre-create row   |  status='running', started_at=now
| in DB            |
+------------------+
        |
        v
+------------------+
| spawn claude     |  asyncio.create_subprocess_exec
| CLI subprocess   |
+------------------+
        |
        v
+------------------+
| stream stdout    |  ring-buffer + SSE fan-out + watchdog
| watchdog ticks   |
+------------------+
        |
   normal exit?       timeout?           crash?
        |                |                  |
        v                v                  v
   POST /api/         status=             status=
   session/finish     'timeout'           'failed'
   (callback from    (watchdog kills)    (subprocess
    Claude after                           exits != 0)
    /self-study
    finishes)
        |
        v
+------------------+
| status='success' |  finished_at=now, note_path set
+------------------+
```

If the callback doesn't arrive (claude died without finishing) — the reconcile job after 5 minutes checks whether the process exists and closes the row as `failed`.

## Where to see the results

After the session finishes:

- **Project dashboard** (`/p/{slug}/`) — the freshest 10–20 lines in "Recent sessions" with status and start time.
- **Live** (`/p/{slug}/live`) — while the session is running, its stdout is here. Removed after completion.
- **Notes** (`/p/{slug}/notes`) — list of md files agents wrote. If `note_path` is recorded — click opens raw-content.
- **AI Usage** (`/p/{slug}/ai-usage`) — tokens / cost of this session (5 minutes after the ingest cron).
- **Aggregated `/`** — incremented success/failed/timeout counters.

## When the session fails

Possible statuses:

- `success` — claude returned exit code 0 and (optionally) DC received the finish callback.
- `failed` — claude returned exit != 0. `error_message` will hold stderr or the last stdout lines.
- `timeout` — the watchdog killed the process after `timeout_minutes`. `error_message`: "timeout after N min".
- `running` (stuck) — process is dead, no callback came, reconcile hasn't fired yet. After 5 minutes it'll move to `failed`.

What to do:

- Open `/p/{slug}/` → recent sessions → click the failed session (if there's a detail link) → read `error_message`.
- If `error_message` is empty — open `/p/{slug}/live` (if still running) or claude's JSONL at `~/.claude/projects/<workdir>/<session>.jsonl`.
- Common causes: the model couldn't find the agent file (typo'd name), no API key, the `/self-study` slash command is not installed, Claude CLI hit a rate limit.

## Customisation

All keys are available at the global level (`/settings`) and at the per-project level (`/p/{slug}/settings`):

- `self_study_command` — the slash command DC invokes. Default: `/self-study`. Change if you renamed your command.
- `self_study_max_turns` — max turns per session (default 50). Lower for short reviews, higher for deep research.
- `self_study_model` — Claude model (default taken from the agent file or a fallback). Overrides the per-agent setting.
- `timeout_minutes` — the watchdog (default 20).
- `agents_per_night` — how many per night.
- `wait_between_sec` — pause between sessions.
- `max_concurrent` — global concurrency cap.

Changes in settings take effect after Save. No uvicorn restart needed.

---

See also:
- [`rotation.md`](rotation.md) — managing the agent list.
- [`live-log.md`](live-log.md) — watching a running session.
- [`notes.md`](notes.md) — where to read the notes.
- Technical: [`../../features/self-study.md`](../../features/self-study.md), [`../../api.md#sessions`](../../api.md), [`../../architecture.md`](../../architecture.md).
