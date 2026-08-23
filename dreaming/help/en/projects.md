## What this section is for

Projects is the list of everything the app manages. Each row is a separate
folder on disk with its own agents, settings and schedule. This is where
projects are created, enabled, disabled, renamed and deleted.

## What is on screen

Every project, disabled ones included. Each shows its slug, a human-readable
label and its working directory.

The slug is not cosmetic: it appears in every `/p/<slug>/...` URL and in the
scheduler's job identifiers.

## What you can do

### Import

The import form takes a path to a root folder. The app looks at its immediate
subfolders — one level down, not recursively — and creates a project for each.
Folders whose name starts with a dot are skipped.

The slug and label come from the folder name. Every imported project is
enabled straight away and gets its scheduler jobs registered.

Whether a folder contains `.claude/` is detected during the scan but does not
block the import: a project without agents will be created, there just will
not be anything to run until you install the starter kit.

### Enabling and disabling

The toggle does more than it looks like. Along with the status it registers or
removes that project's scheduler jobs. A disabled project does not study
overnight and is not scanned on a schedule, but it stays in the list and all
its data is intact.

### Renaming

Changes the label, the slug, or both.

Renaming the slug is supported but has a cost, which the page itself warns
about: scheduler jobs are re-registered under the new slug, and every saved
`/p/<old-slug>/...` link stops working. The slug is checked for shape and
uniqueness — you cannot take one that is in use.

The label can be changed freely; nothing depends on it.

### Deleting

Removes the project from the app and unregisters its scheduler jobs. The folder
on disk is untouched: agents, notes, findings — those are files in your
repository, and the app does not touch them.

## Related sections

- **Global settings** — the defaults every project inherits from.
- **Project settings** — the overrides for one project.
- **Project dashboard** — where to go once a project exists.

## If something looks wrong

- **The import created nothing** — the path does not exist, is not a
  directory, or has no subfolders. Check that you pointed at the root holding
  the projects, not at a project itself.
- **The project exists but its sections are empty** — the starter kit is not
  installed and no directories are set. Open the project dashboard; a
  one-button setup banner is waiting there.
- **Nothing runs overnight** — the project is disabled, or it has no enabled
  agents in the rotation.
- **Bookmarks broke after a rename** — expected; URLs contain the slug. The
  new ones are in the sidebar.
