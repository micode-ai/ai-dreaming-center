## What this section is for

Reflex loops are recurring checks a project runs on itself. Unlike scanners,
which you press a button for and get a snapshot, a loop is a cycle: it keeps
going, accumulates iterations, and shows whether anything changes from pass to
pass.

This screen shows which loops exist and what state they are in.

## Where the data comes from

From the `loops_dir` directory. If it is not set explicitly but
`obsidian_vault` is, `<vault>/03-Team/loops` is used.

Each loop is a markdown file with frontmatter. They are created by the
`/loops-bootstrap` command, started by the button on this page.

## What is on screen

| Column | What it means |
|---|---|
| **name** | The loop's filename. |
| **title** | The title from the frontmatter. |
| **status** | Active, paused, and so on. |
| **iterations** | How many passes have happened. |

**Iterations** is the column that matters. A loop at zero has been created but
never run. A loop whose iterations have not moved in weeks has most likely
stopped, and is worth looking into.

## What you can do

- **Bootstrap** — runs `/loops-bootstrap`: an agent creates a starting set of
  loops for the project. Needed once. It runs as a full session; follow it in
  the Live log.

Loops cannot be edited from here; they are files in the project.

## Related sections

- **Loop templates** — the blueprints loops are made from.
- **Dashboard** — a tile with recent loop runs. It reads the `loop_runs` table
  in the database, and if your installation does not have that table the tile
  says so plainly instead of taking the page down.
- **Live log** — where a running bootstrap is visible.

## If something looks wrong

- **The directory is not set** — set `loops_dir` or `obsidian_vault` in
  project settings.
- **The directory exists but the list is empty** — `/loops-bootstrap` has
  never run.
- **Iterations are not increasing** — the loop is not being run. Check its
  status in the file's frontmatter and the project's schedule.
- **A parse error** — broken frontmatter in one of the files; the error text
  is shown on the page.
