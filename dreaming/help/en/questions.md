## What this section is for

Questions is the agents' mailbox to you. When an agent hits a decision
mid-task that it is not entitled to make alone, it asks and waits. This screen
is the only place such questions can be answered.

While a question sits unanswered, the agent is stopped. So this section is
worth checking at least once a day: one unanswered question can hold a run for
hours.

## How it works

From inside its session the agent calls the app's API and creates a record
with the question text and, if it offered any, the answer options. It then
polls the app until the status changes from pending.

An important detail: the process watchdog knows about a pending question and
**will not kill the session for going quiet** while it waits. An ordinary
session producing no output would be killed on timeout; one waiting for an
answer is not.

When you answer, the text goes back to the agent and it continues from where
it stopped.

## What is on screen

Two lists:

- **Awaiting an answer** — up to the fifty most recent. Each question is shown
  with its text and any options the agent offered.
- **Recently answered** — the last twenty, with what you replied. Useful for
  recalling your own decision.

Search and sorting work over the loaded lists — those fifty and twenty, not
the whole history.

Each question knows which run it came from, so it is clear whose work it is
holding up.

## What you can do

- **Answer** — free text, or one of the offered options. The agent continues
  after you submit.
- **Dismiss** — close the question without answering. The agent receives an
  empty answer and carries on by itself. Use it when the question is no longer
  relevant — the run finished long ago, or was killed.

## Related sections

- **Orchestration** — multi-step runs ask the most questions; a question
  remembers which run and node it belongs to.
- **Live log** — shows that the session is alive and waiting.

## If something looks wrong

- **Empty** — no agent is asking anything right now. That is the normal state.
- **Answered, but the run has not moved** — the agent polls on an interval, so
  a small delay is expected. If it stays stuck, check the Live log to see
  whether the process is still alive: if the session was killed, there is
  nobody left to collect the answer.
- **A question from a run that is long gone** — dismiss it; it affects
  nothing.
