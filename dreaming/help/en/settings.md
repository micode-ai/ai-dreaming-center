## What this section is for

Settings define how the app works: where to find the Claude CLI, which model to
run sessions with, where the data directories live, how many agents to take per
night, the Jira and GitHub credentials.

There are two of them, linked by inheritance:

- **Global settings** — the defaults for every project, stored in
  `config.yaml`.
- **Project settings** — overrides for one project, stored in the database.

## How inheritance works

When the app needs a value it looks, in order:

1. does this project have an override — if so, use it;
2. otherwise use the global value;
3. otherwise the default baked into the code.

That is why every key in project settings offers a choice: **inherit** or
**override**. Switching to inherit deletes the override rather than storing an
empty value — the project returns to the global setting, and if the global one
changes later, the project follows.

One subtlety: an override with an empty field is treated as inherit. You cannot
use the interface to make a project's value blank while the global one is not.

## Type coercion

A field keeps the same type as the global value. If the global value is a
number and you type something that is not, the app **silently keeps the
previous value** without complaining. If you expected a setting to change and
behaviour did not, check that you entered a number and not a word.

Checkboxes left unticked are saved as off: an absent checkbox in the form is an
explicit no, not a "leave it alone".

## Sections in the menu

A separate block at the bottom of the project settings page: tick the sections
this project needs. Unticked ones leave the sidebar.

Three things worth knowing.

**Hiding is about the menu, not about access.** A hidden section stays
reachable by direct link and by links from other sections; it does not 404.
Bookmarks keep working.

**The dashboard and settings cannot be hidden.** The first is the project's
entry point, the second is the only place to bring the rest back. They have no
checkboxes, and an attempt to unset them around the form is ignored.

**What is stored is the hidden list, not the visible one.** So a section added
to the app later shows up everywhere by default, instead of being invisible in
every project configured before it existed.

The help page still lists **every** section, marking the hidden ones: that is
where you decide whether you need a section, and hiding what you switched off
would remove your way of reconsidering.

## Directory autoconfig

Directory keys have a button beside them that creates the default directory and
writes its path into the setting at once. Easier than typing a path, and it
rules out a typo. The one-button setup on the project dashboard does the same
for every directory at once.

## What you can do

- **Global settings** — fill in and save; the file is re-read immediately
  afterwards.
- **Project settings** — for each key, choose inherit or override and set a
  value.
- **Create a directory** — the autoconfig button on directory keys.

## Related sections

- **Projects** — where projects are created, enabled and deleted.
- **Project dashboard** — the one-button setup banner.
- Nearly every section depends on some directory key: when a section is empty
  and complains about a directory, the key is set here.

## If something looks wrong

- **A setting did not save** — most likely a value of the wrong type, silently
  discarded. Check the numeric fields.
- **A project does not see a change to global settings** — it has an override
  on that key. Switch it to inherit.
- **You cannot clear a project's value** — that is by design: an empty field
  means inherit.
- **A section complains about an unconfigured directory** — use the autoconfig
  button; it creates the folder and writes the path.
