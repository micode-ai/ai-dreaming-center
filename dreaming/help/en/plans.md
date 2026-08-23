## What this section is for

Plans are step-by-step work plans held as markdown files with a checklist. The
app computes progress from them: how many items are ticked, how many are left,
what percentage is done. A plan can be handed to the orchestrator to carry out.

Plans are written by agents — including the orchestrator, which starts a plan
for every run.

## Where the data comes from

From the `plans_dir` directory. If it is not set but `obsidian_vault` is,
`<vault>/03-Team/plans` is used.

The files are created by the `plans-extract` command, started by the button on
this page, and by the orchestrator as it works.

## What is on screen

| Column | What it means |
|---|---|
| **name** | The plan's filename. |
| **title** | The title from the frontmatter. |
| **status** | The plan's state. |
| **progress** | Items ticked out of the total, as a count and a percentage. |
| **refs** | Links: a GitHub issue, an orchestration run against this plan. |

Progress is counted from the checkboxes in the text, not taken from the
frontmatter. So it always matches the file's contents: when an agent ticks an
item, the percentage moves on its own.

Clicking a row opens the whole plan with the markdown rendered.

## What you can do

- **Extract** — run `plans-extract`: an agent assembles a plan from what it
  finds in the project.
- **Open** — the plan's full text.
- **Change the status** — rewrites the frontmatter line.
- **Delete** — remove the plan file.
- **Send to orchestration** — the orchestrator takes the plan as its goal and
  works through the items. The run is linked from the frontmatter.
- **File a GitHub issue** — from the plan, with a link back into the app.

## Related sections

- **Orchestration** — every run writes itself a plan at
  `docs/plans/<run_id>.md`. If that directory is the same as `plans_dir`, run
  plans show up here too.
- **Ideas** and **Findings** — where the task a plan is written for usually
  comes from.

## If something looks wrong

- **The directory is not set** — set `plans_dir` or `obsidian_vault` in
  project settings.
- **The directory exists but holds no plans** — `plans-extract` has never run,
  and the orchestrator writes its plans to `docs/plans/`, which may be a
  different directory.
- **Progress is always zero** — the file has no `- [ ]` checkboxes, so there
  is nothing to count.
- **A parse error** — broken frontmatter; the error text is shown on the page.
