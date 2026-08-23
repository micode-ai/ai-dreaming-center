## What this section is for

The dashboard is the project's landing page and the answer to "what has been
going on here". A summary of this week's sessions, the last twenty runs, what
is running right now, and short tiles for orchestration, evolutions and loops.

It is the only screen that shows the project as a whole; every other section
covers one specific part of it.

## What is on screen

### The setup banner

If the project is missing its starter kit or has no working directories
configured, a yellow banner appears at the top with a **one-button** setup. It
copies the missing files into `.claude/` and creates the directories that are
absent from settings. The operation is idempotent — anything already there is
left alone — so pressing it again is safe. While the banner is up, several
sections will be empty: they have nowhere to read from.

### The week's metrics

Counted from Monday 00:00 UTC over the self-study session table:

| Metric | What it is |
|---|---|
| **Week total** | The sum of the statuses below. |
| **success** | The session finished and wrote a note. |
| **no_gap** | The session ran, but the agent found nothing to improve. A normal outcome, not an error. |
| **failed** | The session crashed. |
| **timeout** | The session ran past its limit and was killed. |

Currently-running sessions are counted separately: a row with status
`running`, or with no finish time recorded.

The week is always the current calendar week. On Monday morning the counters
reset — that is not data loss; the session history is untouched.

### Recent sessions

A table of the last twenty runs: agent, status, topic, start time. Search and
sorting work **over those twenty rows only** — this is a browser-side filter,
not a database query. If a session is not in the list, searching will not find
it either.

Per row: **log** — the session's full output, **stop** — kill a running one,
**delete** — remove the row from history.

### Tiles

Three short summaries — orchestration, evolutions, loops. Each is built so it
cannot take the page down: if its data source is missing or raises, the tile
shows an error and the rest of the dashboard carries on.

### Active runs

The processes alive right now, each with a kill button. Both self-study
sessions and command runs (articles, creatives, orchestration) appear here.

## What you can do

- **One-button setup** — install the starter kit and create the directories.
- **Open a session log** — the full output, including a failure's error.
- **Kill a session** — when it has hung, or was started by mistake.
- **Delete a record** — remove a session from the history. Files it managed to
  write stay on disk.
- **Force-close stale** — mark every "running" row for this project as
  cancelled. Needed when the app was restarted and the database still holds
  sessions whose processes are long gone.

## Related sections

- **Rotation** — who studies next.
- **Live log** — the output while a session runs.
- **Notes** — what the successful sessions produced.
- **Orchestration**, **Evolutions**, **Reflex Loops** — the full versions of
  what the tiles reduce to two numbers.

## If something looks wrong

- **Every metric is zero early in the week** — that is correct; counting
  starts on Monday.
- **A session sits in `running` with no process** — the app was restarted. The
  scheduler sweeps such rows on its own, but "Force-close stale" does it now.
- **A tile shows an error** — its data source is unreachable, most often a
  directory that was never set in project settings.
