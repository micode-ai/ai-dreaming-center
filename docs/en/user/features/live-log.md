# Live session log

`/p/{slug}/live` — here you see the stdout of every running session in the project in real time. Use it to:
- Watch a starting session (confirm Claude actually began working).
- Debug if a session is stuck.
- Manually stop (the `Kill` button).

## Contents

- [What the page shows](#what-the-page-shows)
- [How to read the stream](#how-to-read-the-stream)
- [The Kill button](#the-kill-button)
- [If nothing is running](#if-nothing-is-running)
- [Auto-scroll and stream end](#auto-scroll-and-stream-end)

## What the page shows

Open `/p/{slug}/live`. If the project has running sessions — you'll see one block per session:

- Heading with the agent name (monospace) and slug-key (`{slug}:{agent}`).
- A `Kill` button in the corner — red text, regular border.
- A black `<pre>` block with scroll, max-height 96 (Tailwind units). stdout streams into it.

If there are several sessions — blocks stack vertically, each with its own streamer.

## How to read the stream

Claude CLI emits stdout in JSONL format (one JSON object per line). DC shows them **as-is** — no parsing, raw text. That gives you maximum transparency but requires understanding the format.

Typical lines:

- `{"type":"session_start","model":"claude-sonnet-4-5","cwd":"..."}` — Claude started.
- `{"type":"assistant_message","content":"..."}` — the model generated text.
- `{"type":"tool_use","name":"Read","input":{"file_path":"..."}}` — the model decided to use a tool. Here — Read (read a file).
- `{"type":"tool_result","content":"...","is_error":false}` — tool result.
- `{"type":"assistant_message","content":"..."}` — model's follow-up.
- ... repeats ...
- `{"type":"result","subtype":"success","total_cost_usd":0.42,"num_turns":15}` — session ended successfully.
- `{"type":"result","subtype":"error_max_turns"}` — ran out of max_turns.

What to look for:
- The string `is_error":true` — a tool returned an error.
- `subtype` in the final `result` — success / error_max_turns / error / etc.
- `cost_usd` — how much the session cost.
- A long absence of new lines — claude is thinking (model is responding) or stuck.

## The Kill button

The `Kill` button (red text, clickable for a running session) is a POST to `/p/{slug}/live/kill/{agent}`.

What happens:
1. DC finds the subprocess by the key `{slug}:{agent}` in the running table.
2. Sends `process.terminate()` (SIGTERM on Unix, terminate on Windows).
3. Waits up to 5 seconds for graceful shutdown.
4. If the process is still alive — `process.kill()` (SIGKILL / forceful).
5. DB row is marked `status='failed'`, `error_message='killed by user'`.
6. The `/live` page reloads.
7. `KeepAwake` (on Windows), if this was the last session — lets the machine sleep.

Click Kill when:
- The model is clearly looping (the same lines keep repeating).
- The session has been stuck on the same step too long (a tool invoked something very slow).
- You urgently need to free a slot for another session.

After Kill, claude's JSONL at `~/.claude/projects/<workdir>/<session>.jsonl` stays — you can do a post-mortem.

## If nothing is running

If the page has no running sessions — you'll see only the text "Ничего не запущено" (Nothing is running). No pre blocks.

To start something — go to [`rotation.md`](rotation.md), click `Start session` next to an agent, and you'll be redirected here.

## Auto-scroll and stream end

Streamer logic:
- Every new line is appended to `<pre>` via a JS event listener.
- `target.scrollTop = target.scrollHeight` — pre always scrolls to the bottom.
- When the server sends the SSE event `end` — JS closes the EventSource and adds the line `[stream ended]` to pre.
- If by that point you've scrolled up by hand — auto-scroll will still jump back down. (Sadly, no save-scroll-position.)

Technically `/live/stream/{agent}` is an SSE endpoint (Server-Sent Events) via `sse-starlette`. Each stdout line of one process is fanned out to all subscribers of one agent: you can open `/live` in multiple tabs — all will see the same.

After `[stream ended]` the page won't reload itself. Refresh to make the block disappear from the list.

---

See also:
- [`self-study.md`](self-study.md) — what actually gets started.
- [`rotation.md`](rotation.md) — the Start session button.
- [`orchestration.md`](orchestration.md) — Roman runs have their own live mechanism (polling, not SSE).
- Technical: [`../../api.md`](../../api.md), [`../../routes.md`](../../routes.md), [`../../services.md`](../../services.md).
