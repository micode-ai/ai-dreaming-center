## What this section is for

Ideas are product proposals the scanner found: what could be added or improved
in the product, not in the code. Technical problems live in Findings; this is
about functionality and user value.

From an idea you can file a Jira task or a GitHub issue, propose an article
about it, or send it to orchestration to be built.

## Where the data comes from

From the `product_ideas_dir` directory, a project setting. The files are
written by the `product-idea-scan` command, started by the button on this
page. Each idea is a markdown file with frontmatter.

Like tech-debt findings, ideas are edited in place: a status change is a
rewritten frontmatter line. They live in the project and travel with it in git.

## What is on screen

| Column | What it means |
|---|---|
| **id** | The idea's identifier, which is also its filename. |
| **title** | The gist of the proposal. |
| **status** | The stage it is at. Sorted by meaning, not alphabetically. |
| **priority** | Priority, also with meaningful sorting. |
| **created** | When the idea appeared. |
| **refs** | External links: the Jira task, GitHub issue or proposed article filed for it. |

Below the headers are per-column filters; each row starts with a checkbox for
bulk actions. Clicking a row opens the full text of the idea with the markdown
rendered.

## What you can do

- **Scan** — run `product-idea-scan` and refresh the list.
- **Open an idea** — the full description.
- **Change the status** — the field accepts any value.
- **File a Jira task** — creates a Task and writes its key back into the
  idea's frontmatter. Requires a configured Jira email and API token.
- **File a GitHub issue** — the same for GitHub; the URL is saved to the
  frontmatter.
- **Propose an article** — turns the idea into an article proposal. The
  supporting evidence is the idea's own title and file — something checkable,
  because it exists on disk. The proposal then lives in the Articles section.
- **Send to orchestration** — start the orchestrator with this idea as its
  goal.

Links to whatever you filed are saved into the frontmatter, so you cannot file
the same idea twice by accident — the `refs` column shows it has already gone
somewhere.

## Related sections

- **Findings** — built the same way, but for technical problems.
- **Articles** — where an idea goes once you propose an article from it.
- **Orchestration** — where an idea sent to be built is carried out.

## If something looks wrong

- **It says the directory is not set** — set `product_ideas_dir` in project
  settings, or use the one-button setup on the dashboard.
- **The directory exists but the list is empty** — the scan has never run.
- **Jira is not created** — the Jira email and API token are not configured in
  global settings.
- **A parse error** — broken frontmatter in one of the files; the error text
  is shown on the page.
