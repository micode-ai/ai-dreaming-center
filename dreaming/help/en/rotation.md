## What this section is for

Rotation is the agents' self-study queue. Every night the scheduler picks a
few of the project's agents and runs a `/self-study` session for each: the
agent reads its own code, writes a note into `docs/wiki/learning/`, and marks
itself as studied. This screen shows who is queued, who studied last and when,
and who goes next.

The agent list does not come from the database — it is read off disk, from the
`.claude/agents/` folder of the project's working directory. Every time you
open this page, new agent files are added to the rotation automatically at
tier 2 and enabled. You cannot remove an agent from the rotation here; it
disappears when its file does.

## What is on screen

One table row per agent:

| Column | What it means |
|---|---|
| **agent** | The agent's filename in `.claude/agents/`, without the extension. |
| **tier** | 1, 2 or 3. Affects queue order only as a tie-breaker: lower goes first. |
| **enabled** | `✓` — takes part in the nightly rotation, `—` — skipped. |
| **last_studied** | When the agent last finished a self-study session. Empty means never. |

Above the table: search and a filter reset. The `agent`, `tier` and
`last_studied` headers are clickable to sort.

If the starter kit is missing or out of date, a yellow banner appears at the
top with an **Install starter kit** / **Update starter kit** button. Without
it the project has no `/self-study` command and sessions fail immediately.

## What you can do

- **Change the tier** — the dropdown in the `tier` column. Saves immediately.
- **Enable or disable an agent** — the `✓` / `—` button. A disabled agent stays
  in the list but the nightly rotation skips it.
- **Start session** — run self-study right now instead of waiting for the
  night. The button only appears when the agent has no session running. After
  starting, the app sends you to the Live log, where the process output
  streams.

## How the nightly picks are made

The scheduler takes the first N rows in this order:

1. Agents that have never studied (`last_studied` empty) come first.
2. Then by last-studied date, oldest first.
3. On the same date, by tier, 1 through 3.
4. On a full tie, alphabetically.

Disabled agents do not take part. How many agents run per night, and when, are
the `agents_per_night` setting and the schedule in project settings.

The practical consequence: tier is not a priority in the usual sense. A tier-3
agent that has not studied for a month goes before a tier-1 agent that studied
yesterday. Tier only settles ties between equal dates.

## Related sections

- **Live log** — the running session's output as it happens.
- **Notes** — what the agents wrote up afterwards.
- **Dashboard** — the week's summary: how many sessions ran, how many failed.
- **Topics** — meant as the way to tell an agent what to study.

## Known limitation: topics do not reach the session

Custom topics from the Topics section **currently have no effect on a
session**. The topics block is assembled and then dropped before the spawn:
injecting it into the prompt makes the session either hang with no output or
switch into a mode where it denies itself every write to disk — the note is
never saved and the completion callback never fires. The log shows it as
`dropping N-char topics block`.

So a session always starts as a clean `/self-study <agent>` command. You can
keep topics, but for now they work as a note for a human, not as input for
an agent.

## If something looks wrong

- **The table is empty** — the project's `.claude/agents/` has no agent files,
  or the working directory in project settings points somewhere else.
- **Sessions fail instantly** — almost always a missing starter kit. Check the
  banner at the top.
- **`last_studied` does not update** even though the session ran — the agent
  never reached the completion callback. The Live log shows why: a failed
  session leaves an error line there.
