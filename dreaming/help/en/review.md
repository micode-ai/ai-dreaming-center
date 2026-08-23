## What this section is for

Review is everything awaiting your decision, on one screen. It has no data of
its own: it gathers three streams from neighbouring sections and shows only
what genuinely needs attention.

The point is to avoid walking through five sections in turn asking "what has
piled up here".

## What lands here

### Proposed evolutions

From the evolutions directory — those whose status is `proposed` **or empty**.
An empty status counts as proposed deliberately: that is exactly how the
`/evolve-agent` command writes a new proposal.

The agent, the title, and a conflict marker are shown.

### Urgent findings

From the tech-debt directory — only those that are both `open` and of
`high`, `urgent` or `critical` priority. Nothing else appears: a
medium-priority finding, or one already closed, will not show on this screen.

### Recent sidecar findings

The last ten, sorted by the modification time of their source file.

## What to keep in mind

This is a display, not a store. Each item links to its real page, and that is
where the actions are. Nothing can be changed from here.

Each of the three blocks is read independently, with its own error handling:
if the evolutions directory is broken, the other two still render. An empty
block therefore means one of two things — either it really is empty, or its
source is unreachable. Visiting the corresponding section tells you which.

## Related sections

- **Evolutions** — the full list of proposals and the apply button.
- **Findings** — every finding, not only the urgent ones.
- **Sidecar findings** — the whole stream, with a severity filter.

## If something looks wrong

- **Entirely empty** — either there is nothing to triage, or none of the three
  directories is configured. Check project settings.
- **Findings exist in Findings but not here** — their priority or status does
  not qualify. Only open, high-priority findings reach this screen.
- **A block is empty while its own section is full** — the source failed to
  read; the error goes to the app's log, not to the screen.
