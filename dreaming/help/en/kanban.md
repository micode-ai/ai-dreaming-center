## What this section is for

Plan answers "who studies over the next five days" and gives you a form for
entering a topic. It is not a drag-and-drop task board: the layout is computed
from the rotation, and you cannot move an agent between days by hand.

## What is on screen

### The five-day layout

Five columns starting today. Each holds as many agents as the scheduler takes
per night (the `agents_per_night` setting, five by default).

The order is exactly the one the scheduler uses at night: agents that have
never studied first, then by last-studied date from oldest to newest, ties
broken by tier. Disabled agents do not appear.

Each agent shows its tier and how many sessions it has had in total.

This is a forecast, not a timetable. It is recomputed every time you open the
page and will shift if you enable or disable an agent, change
`agents_per_night`, or start a session by hand. If there are fewer agents than
five days × N, the later columns are empty — that is normal and means everyone
completes a full round sooner.

### Custom topics

Below: the list of entered topics and the add form. Fields are title
(required), module, target agents, what to study, and why it matters.

## What you can do

- **Add a topic** — the form at the bottom of the page.
- **Delete a topic** — the button on the topic's row.
- The layout cannot be edited directly. You influence it through Rotation —
  enabling and disabling agents, changing tiers — and through
  `agents_per_night` in project settings.

## Important: topics do not reach the agent

A topic you enter **will not appear in a self-study session**. The topics
block is assembled and dropped before the spawn, because injecting it breaks
the session — it hangs, or starts refusing its own writes to disk. See the
Rotation help for detail.

While that holds, the add form works as a notebook: the topic is saved and
visible, but no agent will read it.

## Related sections

- **Rotation** — the source of the layout, and the only place you can affect
  it.
- **Topics** — the weekly checklist plus the same custom topics list.
- **Dashboard** — what actually ran out of what was planned.

## If something looks wrong

- **The columns are empty** — the rotation has no enabled agents, or the
  project has no agent files at all.
- **The layout did not match what ran overnight** — expected, if anything
  changed in between: someone studied by hand, an agent was disabled, a
  setting moved. The forecast is built at the moment you open the page.
- **Every agent is in the first column** — there are fewer of them than
  `agents_per_night`, so they all fit in one night.
