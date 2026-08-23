## What this section is for

Evolutions are agents' proposals for changing their own instructions. After
working, an agent notices that its description is inaccurate or incomplete and
writes a proposal: here is what should be fixed in my definition.

This is the only mechanism by which agents change themselves, and it
deliberately goes through your approval: the proposal sits as a file until you
apply it.

## Where the data comes from

From the `evolutions_dir` directory. If it is not set, the app tries
`context_overrides_dir`, then `<working_dir>/.claude/agents/_context`.

Every `.md` is read recursively, except names starting with `_` or a dot. The
agent name comes from the frontmatter, or, if absent there, from the name of
the folder the file sits in.

**These files are untracked in git and easy to lose.** A `git stash -u` run
from orchestration to get a clean tree once swept them away. The orchestrator
is now explicitly forbidden from doing that, and the directory is gitignored.
If the section suddenly looks empty, the proposals are most likely alive in
the stash: look in `stash@{N}^3`.

## What is on screen

| Column | What it means |
|---|---|
| **agent** | Whose instructions the proposal would change. |
| **title** | The gist of the proposal. |
| **status** | New, accepted, rejected. |
| **conflict** | The proposal clashes with the agent file's current state. |
| **refs** | Links: a GitHub issue, an orchestration run applying it. |

At the top, a rubric summary: how many proposals there are, how many carry a
score, and how they split across "apply automatically", "needs review",
"reject" and "score incomplete".

The rubric is a hint, not a decision. Even `auto` is only applied when you
press the button.

## What you can do

- **Open** — the full proposal text.
- **Change the status** — rewrites the frontmatter line.
- **Apply** — starts the orchestrator, which makes the change to the agent
  file. The run is linked from the frontmatter.
- **File a GitHub issue** — from the proposal.
- **Delete** — remove the proposal file.

## Related sections

- **Rotation** — proposals come out of self-study sessions.
- **Orchestration** — where applying happens.
- **Review** — the roll-up screen where evolutions appear alongside everything
  else awaiting a decision.

## If something looks wrong

- **Empty although sessions ran** — the agents found nothing to propose, or
  they write to a different directory: check `evolutions_dir` against what the
  agents' own instructions say.
- **The section emptied all at once** — see the `git stash -u` note above;
  check the stash.
- **A file exists but is not listed** — its name starts with `_` or a dot.
- **Marked as a conflict** — the agent file changed after the proposal was
  written. Read it yourself before applying.
