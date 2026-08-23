## What this section is for

Findings is the flat list of everything the tech-debt scanner turned up. Each
finding is its own markdown file with frontmatter: what is wrong, in which
module, how urgent, how hard to fix, and whether an agent could fix it alone.

This is a working screen: from here you close a finding, file a GitHub issue
for it, or hand it to the orchestrator to carry out.

## Where the data comes from

From the `tech_debt_dir` directory, set in project settings. The files are
written by the scanner — the `tech-debt-scan` command, started by the button
on this page or on a schedule. The header shows when the scan last ran and
whether one is running now.

The app reads and edits those files directly. Every status change is a
rewritten frontmatter line, not a database write. That means findings survive
reinstalling the app and travel with the project in git.

## What is on screen

A table with these columns:

| Column | What it means |
|---|---|
| **id** | The finding's identifier, which is also its filename. |
| **title** | A short statement of the problem. |
| **status** | `open`, `in-progress`, `closed`, `dropped`, `blocked`, or any other value an agent writes. |
| **priority** | Urgency. Sorted by meaning, not alphabetically. |
| **module** | The part of the project the finding belongs to. |
| **complexity** | How much work the fix is estimated to be. |
| **autonomy** | Whether an agent could fix this without a human. |
| **confidence** | How sure the scanner is that this is a problem at all. |
| **created** | When the finding appeared. |
| **refs** | Links: the GitHub issue filed for it, and similar. |

Below the headers is a per-column filter row, plus status and module filters
carried in the URL. Filtering runs over the loaded list in the browser.

Each row starts with a checkbox: findings can be selected and closed or
deleted in bulk.

## What you can do

- **Run a scan** — re-read the project and refresh the list.
- **Open a finding** — the full text with the description and proposed fix.
- **Change the status** — the field accepts any value; picking a sensible one
  is up to you, the app validates nothing.
- **Close** — the common case of a status change, given its own button.
- **Delete** — remove the finding's file for good.
- **File a GitHub issue** — creates an issue titled `[<project>] <title>`,
  with the finding as the body and a link back into the app. Labels:
  `tech-debt` plus the priority. The resulting issue URL is written back into
  the frontmatter, so you cannot file the same finding twice by accident. The
  repository comes from the `github_repo` setting, or is inferred from the
  working directory.
- **Send to orchestration** — start the orchestrator with this finding as its
  goal. Follow it from there in the Orchestration section.
- **Bulk actions** — close or delete everything selected.

## Related sections

- **Tech debt overview** — the same data aggregated by module and priority,
  without the row-by-row detail.
- **Orchestration** — where a finding goes once you send it to be worked on.
- **Review** — review results land there; it is a separate stream of findings.
- **Sidecar findings** — another independent source of findings.

## If something looks wrong

- **Empty, with a message that the directory is not set** — set
  `tech_debt_dir` in project settings, or use the one-button setup on the
  dashboard.
- **The directory is set but the list is empty** — the scan has never run.
  The button is at the top of the page.
- **A parse error instead of the list** — one of the finding files has broken
  frontmatter. The error text is shown on the page.
- **The GitHub issue is not created** — either `github_repo` is not
  configured, or the working directory has no authenticated `gh` client
  available.
