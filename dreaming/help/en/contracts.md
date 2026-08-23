## What this section is for

Contracts are specifications: agreements about how a module or a page is
supposed to behave. Each contract is a markdown file with frontmatter. The
point is to have the behaviour written down separately from the code, so you
can check whether the two have drifted apart.

From a contract you can start an audit: the orchestrator walks the code and
compares it against what is written.

## Where the data comes from

From the `contracts_dir` directory. If it is not set explicitly but
`obsidian_vault` is, the app uses `<vault>/03-Team/specs/contracts`.

Every `.md` file is read recursively, except those whose name starts with `_`
or a dot — a convention that lets templates and helper files live in the same
directory without cluttering the list.

The files are written and updated by the `contracts-scan` command, started by
the button on this page.

## What is on screen

| Column | What it means |
|---|---|
| **name** | The contract's name. |
| **kind** | `module`, `page` or `unknown` — what is being described. |
| **module / page** | What the contract covers. |
| **status** | The contract's state. Sorted by meaning. |
| **last review** | When the contract was last checked against the code. |
| **refs** | Links: a GitHub issue filed for it, an orchestration run against it. |

The **last review** column is the most useful one. A contract that has not
been checked in a long time has probably drifted from the code, and cannot be
trusted.

## What you can do

- **Scan** — run `contracts-scan` and refresh the list.
- **Open** — a detail page with the markdown rendered.
- **Change the status** — rewrites the frontmatter line.
- **Delete** — remove the contract file.
- **Audit via orchestration** — starts the orchestrator comparing the code
  against the contract. The run is linked from the frontmatter, so it is
  visible that an audit already happened.
- **File a GitHub issue** — from the contract, with a link back into the app.

## Related sections

- **Orchestration** — where the audit runs.
- **Findings** — discrepancies found during an audit can land there.
- **Wiki** — descriptive documentation; contracts differ in that they state
  checkable requirements rather than explaining how something works.

## If something looks wrong

- **The directory is not set** — set `contracts_dir` (or `obsidian_vault`,
  which the default path is derived from) in project settings.
- **The directory exists but the list is empty** — either the scan never ran,
  or every file in it starts with `_` or a dot and is therefore skipped.
- **A file exists but is not listed** — check the first character of its name.
- **A parse error** — broken frontmatter; the error text is shown on the page.
