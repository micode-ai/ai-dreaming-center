## What this section is for

AI usage is how many tokens and how much money the agents' work consumed.
Inside a project it covers that project; the global section covers all of them
at once.

## Where the data comes from

The app parses the Claude Code session JSONL files the CLI writes for itself
and lays them out in its own table. A scheduled background job does this — not
the page load.

Two consequences follow. First, a fresh session does not appear in the metrics
immediately, only after the next parse pass. Second, what lands here is not
limited to sessions started from the app: if a session file can be matched to a
project it is counted, even if you were working in a terminal by hand.

Sessions whose working directory matches no project are simply skipped.

## What is on screen

- **The 7-day and 30-day tiles** — always computed without your filters. That
  is deliberate: while you cycle through periods and models, those two numbers
  stay as a fixed reference.
- **Totals for the selected period** — tokens, cost, number of sessions.
- **By model** — the spend broken down.
- **By day** — the trend. Days with no activity are not dropped from the
  series but shown as zeros, so a gap reads as a gap rather than squeezing the
  chart.
- **Main session versus side chains** — how much went to the main thread and
  how much to subagents. Useful for working out what is actually expensive.
- **Top sessions** — the most costly ones.

## Filters

- **Period** — today, 7 days, 30 days, all time.
- **Model** — narrow everything to one model. The model list is built from
  what actually appears in this project's data.

The filters affect every block except the two reference tiles.

## Related sections

- **Cascade costs** — spend broken down by orchestration run rather than by
  model and day.
- **Dashboard** — how many sessions ran; this is what they cost.

## If something looks wrong

- **Empty on a new project** — the background parse has not run yet, or there
  are no session files.
- **A fresh session is missing** — expected until the next parse pass.
- **There is spend but the model is not in the filter** — the filter is built
  from this project's data; a model seen only in another project will not
  appear here.
- **The numbers are noticeably lower than expected** — some session files did
  not match the project. Usually those are sessions started from a home
  directory rather than the project's working directory.
