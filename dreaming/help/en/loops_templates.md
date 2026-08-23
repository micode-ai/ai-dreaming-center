## What this section is for

Loop templates are the catalogue of blueprints reflex loops are created from.
This is the one section of the app with full editing: a template can be
created, changed and deleted right here.

## Where the data comes from

From the `loops_templates_dir` directory. If it is not set,
`<working_dir>/.claude/loops/templates` is used.

Sixteen starting templates are placed automatically during the project's
initial setup. Anything beyond those you add yourself.

## What is on screen

The list of templates. Clicking one opens the edit form.

Template fields:

| Field | What it is |
|---|---|
| **slug** | The identifier and the filename. Lowercase letters, digits and hyphens only; the first and last character must be a letter or digit. |
| **name** | The human-readable name. Falls back to the slug if left empty. |
| **description** | What the template is for. |
| **engine** | The execution engine, `loop` by default. |
| **preset** | A preset, if the engine supports one. |
| **max_iterations** | A cap on the number of passes. Empty means no cap. A non-numeric value silently becomes "no cap". |
| **tags** | Comma-separated labels. |
| **team** | The agent team, `auto` by default. |
| **body** | The template body — the instruction itself. |

A template is saved as a markdown file with YAML frontmatter: the fields above
are the frontmatter, `body` is the text beneath it.

## What you can do

- **Create a template** — the new-template form.
- **Edit** — open an existing one and save.
- **Delete** — remove the template file.

Saving under an existing slug overwrites that template. There is no separate
confirmation for it, so changing the slug of an existing template creates a
second one rather than renaming the first.

## Related sections

- **Reflex Loops** — the loops themselves, created from these templates.

## If something looks wrong

- **It says the directory is not configured** — set `loops_templates_dir` in
  project settings, or make sure the project has a working directory, which
  the default path is built from.
- **It refuses to save, complaining about the slug** — it contains uppercase
  letters, underscores or spaces, or starts or ends with a hyphen.
- **`max_iterations` did not save** — what you typed was not a number; the
  field silently became empty, meaning no cap.
- **The list is empty on a new project** — initial setup never ran. Use the
  one-button setup on the dashboard.
