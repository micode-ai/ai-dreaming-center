## What this section is for

Sidecar findings are remarks from external reviewers, delivered as JSON
reports. This is a separate stream from the tech-debt scanner: there an agent
writes findings as markdown, here a third-party tool drops reports in a
machine-readable form.

The section is read-only. You cannot close a finding or change its status from
here — it is a display of what was found outside.

## Where the data comes from

From the `sidecar_findings_dir` directory. If it is not set explicitly but
`obsidian_vault` is, `<vault>/03-Team/sidecar-findings` is used.

The app reads the JSON reports and flattens them into a list of findings. One
row is one finding, not one report: a file with ten remarks produces ten rows.

## What is on screen

| Column | What it means |
|---|---|
| **reviewer** | Who found it — the tool or reviewer's name. |
| **id** | The finding's identifier within the report. |
| **title** | The remark itself. |
| **severity** | How serious it is. |
| **module** | The part of the project. |
| **file** | The specific file. |
| **rule** | The rule that fired. |

At the top, a severity filter. Its values are collected from what actually
appears in the reports rather than from a fixed set: if a reviewer uses its own
labels, they show up in the filter as they are.

## What you can do

- **Filter by severity** — the only action on the page.

For findings to appear here, an external tool has to place reports in the
directory. The app does not run them.

## Related sections

- **Review** — the ten most recent sidecar findings appear in the roll-up,
  alongside evolutions and urgent debt.
- **Findings** — a parallel stream of findings, with its own scanner and its
  own actions.

## If something looks wrong

- **The directory is not set** — set `sidecar_findings_dir` or
  `obsidian_vault` in project settings.
- **The directory exists but holds no findings** — the external reviewer has
  never run, or writes its reports somewhere else.
- **A parse error** — one of the JSON files is not in the shape the app
  expects. The error text is shown on the page.
- **The severity filter is empty** — no finding has a severity field filled
  in.
