## What this section is for

Tech debt overview: the same findings as the Findings list, reduced to a few
numbers. How many there are, how they split by status, which modules have
collected the most. A screen for looking from above, not for working on a
specific finding.

If you need to do something with a finding — open it, close it, file an issue —
that is the neighbouring Findings section.

## What is on screen

- **Total** — how many findings sit in the directory.
- **By status** — how many are `open`, `closed`, `in-progress` and so on,
  sorted by count descending. A finding with no status counts as `unknown`.
- **By module** — the top ten modules by number of findings. Findings with no
  module are grouped under `—`.

The cut-off at ten modules is display only. The data may hold more; the full
list is visible in Findings through the module filter.

## Where the data comes from

From the same `tech_debt_dir` as the list: the app reads the finding files and
counts them on the fly every time you open the page. This screen has no
database of its own and no cache — the numbers always match the files on disk.

## What you can do

- **Run a scan** — re-read the project with the `tech-debt-scan` command.
- Everything else lives in the Findings section.

## How to read it

Two things are worth watching.

The first is the share of `open` in the total. If it grows from scan to scan,
debt is accumulating faster than it is being worked off.

The second is the spread across modules. One module holding half the findings
usually does not mean it is badly written — it means it is the largest, or the
most frequently touched. It is a hint about where to look first.

## Related sections

- **Findings** — the same data row by row, with every action.
- **Review** and **Sidecar findings** — other streams of findings; they are
  not included in this overview.
- **Orchestration** — where findings sent to be worked on are carried out.

## If something looks wrong

- **It says the directory is not set** — set `tech_debt_dir` in project
  settings, or use the one-button setup on the dashboard.
- **Everything is zero** — the scan has never run.
- **An error instead of numbers** — broken frontmatter in one of the files;
  the error text is shown here, but the list is the easier place to track it
  down.
