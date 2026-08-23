## What this section is for

Questions is the agents' mailbox to you. When an agent hits a decision
mid-task that it is not entitled to make alone, it asks and waits. This screen
is the only place such questions can be answered.

While a question sits unanswered, the agent is stopped. So this section is
worth checking at least once a day: one unanswered question can hold a run for
hours.

## Why it is usually empty

The question channel is wired into **two commands out of fourteen** —
`/write-article` and `/make-creative`. The others cannot ask: their
instructions carry no such block, deliberately. Scanners produce proposals you
review anyway, and a stalled nightly scan is worse than a low-confidence
finding. The orchestrator is forbidden from asking by a rule of its own and
writes its questions to `docs/plans/<run_id>-questions.md`.

The built-in `AskUserQuestion` tool does **not** arrive here: intercepting
calls to it was never implemented — `claude_session_tail.py` records it as
deferred. Only an explicit HTTP call from a command's text works.

And even the one command that has it treats the channel as an emergency exit:
it asks only when it cannot confirm a fact and refuses to invent one.

So an empty section is the normal state, not a fault.

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

- **Articles** — the only source of questions today. An article card in the
  Writing state links here when the writer is waiting.
- **Orchestration** — does not ask: a rule in its instructions forbids it, and
  it writes missing information to `docs/plans/<run_id>-questions.md` instead.
  A question record still carries run and node fields — the articles page uses
  them to work out which card is waiting.
- **Live log** — shows that the session is alive and waiting.

## If something looks wrong

- **Empty** — no agent is asking anything right now. That is the normal state.
- **Answered, but the run has not moved** — the agent polls on an interval, so
  a small delay is expected. If it stays stuck, check the Live log to see
  whether the process is still alive: if the session was killed, there is
  nobody left to collect the answer.
- **A question from a run that is long gone** — dismiss it; it affects
  nothing.
