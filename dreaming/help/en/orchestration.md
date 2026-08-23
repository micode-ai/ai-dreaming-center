## What this section is for

Orchestration is how you hand over a whole task instead of stepping through it.
You state a goal, the app starts an orchestrator agent, and it breaks the goal
into subtasks, calls other agents, and sees it through. This screen is the list
of such runs and the detail of each.

It is also where findings, ideas, plans and contracts end up when you send them
to be worked on from their own sections.

## How it works

The run record is created before the process starts, so its page opens
instantly and fills in as work happens. Two things come up alongside it: a
reader for the session stream and a watcher for subagents — the stages and
nodes you see in the breakdown come from those.

The orchestrator runs non-interactively, which means it **cannot ask you
anything**. Its instructions account for that and require it to:

- never ask a question; when information is missing, write it to
  `docs/plans/<run_id>-questions.md` and continue with a sensible default;
- always choose rather than stall: when two paths look equal, take the simpler
  one and move on;
- write a plan to `docs/plans/<run_id>.md` immediately and tick off steps as
  it goes;
- report completion explicitly.

It is separately forbidden from destroying untracked files under `.claude/` —
no `git stash -u`, no `git clean -fd`. That is not an abstract precaution: it
once swept away evolution proposals sitting in `.claude/agents/_context/`.

## What is on screen

The list of runs with status, goal and time. Clicking one opens the detail: the
breakdown into stages and nodes, a live event feed, the plan and the artifacts.

While a run is in progress the detail page updates itself.

## What you can do

- **Start** — the goal form. Phrase it so the result is checkable: the
  orchestrator has nobody to ask.
- **Open a run** — detail and live progress.
- **Finish manually** — closes the run and every open stage and node as
  completed. Needed when the process died without reporting and the run is
  stuck as running.
- **Resume** — continue the orchestrator's session from where it stopped.
- **Backfill** — reconstruct a run's data from the saved session.
- **Delete** — remove a run from history.
- **Force-close stale** — close every hung run for the project at once. Needed
  after restarting the app.

## Related sections

- **Questions** — ordinary sessions ask through that section; the orchestrator
  is not allowed to, and writes its questions to a file instead.
- **Findings**, **Ideas**, **Plans**, **Contracts** — where the tasks come
  from.
- **Live log** — the raw process stream, without the stage breakdown.

## If something looks wrong

- **A run is stuck as running with no process** — the app was restarted. Use
  "Finish manually" or "Force-close stale".
- **An empty breakdown on a live run** — the orchestrator has not reached its
  first stage yet. The raw output is in the Live log.
- **The orchestrator stopped halfway** — check
  `docs/plans/<run_id>-questions.md`: it may have hit a question with nobody
  to ask.
- **Old runs named `roman`** — that is what the orchestrator was called before
  May 2026; records from then are kept as they are.
