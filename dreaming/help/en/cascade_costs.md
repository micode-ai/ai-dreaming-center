## What this section is for

Cascade costs is what orchestration runs cost. Not the overall model spend —
that is AI usage — but the per-run breakdown: which run ate how many tokens
and how much money.

Useful when you want to know whether the automation pays for itself: a single
expensive run that never finished stands out immediately here.

## What is on screen

### The period summary

- **Runs** — how many fall inside the window.
- **Total cost** and **total tokens** — the sums across those runs.
- **Events** — how many events were recorded for them.
- **Averages** — cost and tokens per run.
- **By status** — how many completed, failed, were cancelled.

### The run table

One row per run, with its cost, tokens, event count and status.

## Filters

**Period** — presets: today, 7 days, 30 days, all time. The default is 7 days.
An unknown value is silently treated as 7 days.

The window is measured against the run's start time, in UTC. "Today" means
since midnight UTC, not in your own timezone; if you work in the evening and
live east of Greenwich, the day boundary will not match your sense of it.

**Status** — narrow to completed, failed, and so on.

## An important limit

At most **200 runs** are read from the database for the period. Search and
sorting in the table work over those two hundred, in the browser. On a busy
project with "all time" selected, that means you are looking at a recent slice
rather than the whole history — and the summary figures are computed from that
slice, not from every run in the period.

If the numbers look too low, narrow the period: over a short window, two
hundred rows hold everything.

## Related sections

- **Orchestration** — the runs themselves, their progress and outcome.
- **AI usage** — total spend for the project, not only orchestration.

## If something looks wrong

- **Empty** — no orchestration ran in the selected period. Try "all time".
- **Zero cost with non-zero tokens** — cost was never recorded on that run's
  events.
- **The total does not match what you expected** — most likely the 200-run cap
  kicked in; see above.
