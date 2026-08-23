## What this section is for

Notes are what the agents wrote up after self-study. Every successful session
leaves a markdown file: what the agent studied, what it understood, what is
worth fixing. This section lets you read them without going through the file
system.

The app only reads here. The files are created by agents; you cannot edit or
delete them through the interface.

## What is on screen

At the top, the path everything is read from. By default that is
`.claude/agents/learning-notes/` inside the project's working directory; the
path can be overridden with the `learning_notes_dir` key in project settings.
If the directory does not exist, a red marker appears next to the path.

Then a table of files:

| Column | What it means |
|---|---|
| **path** | Path relative to the notes directory. Nested folders are supported and shown as-is. |
| **size** | File size. |

The list is sorted by modification time, newest first, and capped at two
hundred files. Search and sorting work over the loaded list in the browser —
that is, over those two hundred, not over the whole directory.

Clicking a row opens the file's contents on the page, with the markdown
rendered.

## What you can do

- **Find a note** — search by path.
- **Sort** — by path or size.
- **Read** — clicking a row loads the file and renders it.

## Related sections

- **Rotation** — who studied and when; a note appears after a successful
  session.
- **Dashboard** — the week's `success` metric roughly matches the number of
  new notes.
- **Wiki** — the project's more structured knowledge base; self-study notes
  live separately from it.

## If something looks wrong

- **Directory not found** — either the project has never studied, or
  `learning_notes_dir` points elsewhere. Check the path in the page header.
- **Empty although sessions ran** — the sessions ended as `no_gap` (the agent
  had nothing to add) or crashed before writing. Check the statuses on the
  dashboard.
- **A successful session but no new note** — the file may have gone to a
  different directory: the agent writes where its own instructions in
  `.claude/agents/` say, and this page reads what project settings say. Those
  two paths need to agree.
