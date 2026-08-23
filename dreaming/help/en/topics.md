## What this section is for

Topics is the checklist of what the agents ought to study. Two independent
things share the page: a weekly checklist that lives as a file in the project,
and custom topics you enter by hand and that are stored in the app's database.

## What is on screen

### The weekly checklist

Read from `_weekly-learning-checklist.md`. The app looks in two places, in
order:

1. `.claude/agents/lessons/_weekly-learning-checklist.md`
2. `.claude/agents/_weekly-learning-checklist.md`

The first one found wins, and its path is shown on the page. Lines of the form
`- [ ]` and `- [x]` are parsed. If the file is missing and the starter kit
carries one, a button appears to install it.

This part is read-only: you cannot tick an item through the interface. The
file is edited in an editor, or by an agent.

### Custom topics

The list of active topics from the app's database. They are created on the
neighbouring Plan page, which holds the add form. A topic has a title, a
module, target agents, what exactly to study, and why it matters.

## Important: topics do not affect sessions

Custom topics **currently have no effect on self-study**. The topics block is
assembled before a session starts and immediately dropped: injecting it into
the prompt makes the session either hang with no output or switch into a mode
where it denies its own writes to disk, so the note is never saved. The log
shows it as `dropping N-char topics block`.

The agent therefore always receives a clean `/self-study <agent>` command, and
topics work as a note for a human. Recording them is still worth it so an idea
is not lost, but do not expect an agent to read them yet.

The weekly checklist is not affected by this — it is a file in the project,
and an agent reads it itself if its own instructions say to.

## What you can do

- **Install the checklist** — when the file is missing and the starter kit has
  one.
- **Generate topics** — the button runs the `/topics-scan` command: an agent
  walks the project and proposes what is worth studying. The results appear in
  the custom topics list.
- Adding and deleting topics happens on the Plan page.

## Related sections

- **Plan** — the add-topic form and the five-day rotation layout.
- **Rotation** — who studies and when.
- **Notes** — what came out of it.

## If something looks wrong

- **Checklist not found** — the file exists at neither path. Install it with
  the button, or create it by hand.
- **The topics list is empty** — no topic has been entered and `/topics-scan`
  has never run.
- **A topic is entered but the agent ignores it** — correct; see the section
  above on topics not reaching the session.
