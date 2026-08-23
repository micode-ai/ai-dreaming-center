## What this section is for

The live log is a window into the processes running right now. While a session
is alive its output streams here line by line. This is where to look when a run
behaves oddly: hangs, prints nothing, or crashes.

Once a process finishes it disappears from this page. To work out what happened
to a session that already ended, go to the dashboard — every row there has a
**log** button with the full saved output.

## What is on screen

One card per live process in the project. There are two kinds, and both show
up here:

- **Self-study sessions** — started by the rotation or by hand. The card shows
  the agent's name.
- **Command runs** — scanners, article writing, creative assembly,
  orchestration. The card shows the command name, such as `tech-debt-scan` or
  `write-article`.

Output arrives over SSE — a held-open connection, not polling. You do not need
to refresh; lines appear as the process writes them.

Processes whose child has already exited are not shown, even if the internal
record has not been cleaned up yet. Otherwise you would be looking at a card
with a pulsing "live" indicator and not a single new line.

## What you can do

- **Read the output** — line by line, as it happens.
- **Kill** — stop the process. Use it when a session has clearly looped or is
  hanging with no output. Anything it already wrote to disk stays; the session
  record is marked as failed.

## Reading the output

Lines appear exactly as Claude CLI prints them. What to watch for:

- **A long silence at the start** — usually fine: the model is thinking before
  its first response.
- **A line about a denied write** — the session has entered a mode where it
  refuses its own changes to disk. The note will not be saved. For self-study
  there is a known cause: the injected topics block, see the Rotation help.
- **`[error]`** — the session crashed; the error text is persisted and stays
  visible on the dashboard after the session is gone.

## Related sections

- **Rotation** — where self-study sessions come from.
- **Dashboard** — the history of finished runs and their logs.
- **Orchestration** — multi-step runs have their own screen broken down by
  stage; only the raw stream lands here.

## If something looks wrong

- **The page is empty** — nothing is running. That is the normal state for
  most of the day.
- **A card with no lines** — the process started but has printed nothing yet.
  If that lasts more than a few minutes it is most likely waiting for a
  confirmation nobody can give; kill it and check the project settings.
- **The stream stopped** — the SSE connection dropped; refresh the page. The
  process itself is not affected.
